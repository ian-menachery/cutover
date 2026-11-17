"""Load a migration's exports into DuckDB and derive the views the checks read.

Every file loads as text: nothing is type-inferred, so a malformed value
reaches the checks as the string it is instead of silently becoming NULL at
load time. The spec then generates, per entity:

- ``src_<e>`` / ``tgt_<e>``: the raw files, plus ``_row`` (CSV line number).
- ``exp_<e>``: every source row with its key, scope and deferral flags, and
  each mapped field transformed the way the spec says the target should hold
  it (``<field>``), with the raw source value (``<field>__src``) and, for
  value maps, whether the code is missing from the map (``<field>__unmapped``).
- ``act_<e>``: every target row with its cross-reference key and each mapped
  field parsed to the same type (``<field>``) next to its raw text
  (``<field>__raw``). A parent link resolves to the parent's legacy key.
- ``pairs_<e>``: keys that appear exactly once on each side.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from cutover.models import RegisterEntry
from cutover.spec import DEFAULT_SPEC, EntitySpec, FieldSpec, Spec, load_spec

REGISTER_COLUMNS = ("check", "entity", "key", "reason", "ticket")


def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def norm(expr: str) -> str:
    """Blank and whitespace-only cells are absent values."""
    return f"NULLIF(TRIM({expr}), '')"


def _date(expr: str, fmt: str) -> str:
    return f"CAST(try_strptime({expr}, {lit(fmt)}) AS DATE)"


def _money(expr: str) -> str:
    return f"TRY_CAST(REPLACE({expr}, ',', '') AS DECIMAL(18,2))"


@dataclass
class Migration:
    con: duckdb.DuckDBPyConnection
    spec: Spec
    register: list[RegisterEntry]
    present: set[str] = field(default_factory=set)
    problems: dict[str, str] = field(default_factory=dict)

    def rows(self, sql: str) -> list[dict]:
        cur = self.con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    def scalar(self, sql: str):
        return self.con.execute(sql).fetchone()[0]


def _required_columns(e: EntitySpec, side: str) -> list[str]:
    if side == "src":
        return [e.source_key, *(c.field for c in e.exclude_when), *(f.source for f in e.fields)]
    return [e.target_key, e.target_id, *(f.target for f in e.fields)]


def _load_csv(con: duckdb.DuckDBPyConnection, table: str, path: Path, header: list[str]) -> None:
    columns = "{" + ", ".join(f"{lit(c)}: 'VARCHAR'" for c in header) + "}"
    con.execute(
        f"CREATE TABLE {table}__raw AS SELECT * FROM read_csv({lit(str(path))}, header=true, "
        f"auto_detect=false, columns={columns}, delim=',', quote='\"', escape='\"')"
    )
    # rowid is insertion order; with one thread and preserved insertion order,
    # that is file order. Header is line 1, so the first record is line 2.
    con.execute(f"CREATE TABLE {table} AS SELECT rowid + 2 AS _row, * FROM {table}__raw")
    con.execute(f"DROP TABLE {table}__raw")


def read_register(path: Path) -> list[RegisterEntry]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            RegisterEntry(**{c: (row.get(c) or "").strip() for c in REGISTER_COLUMNS})
            for row in csv.DictReader(fh)
        ]


def _in_scope(e: EntitySpec) -> str:
    if not e.exclude_when:
        return "TRUE"
    clauses = []
    for c in e.exclude_when:
        col = norm(ident(c.field))
        if c.equals is not None:
            clauses.append(f"{col} = {lit(c.equals)}")
        if c.before is not None:
            clauses.append(f"{_date(col, c.format or '%Y-%m-%d')} < DATE {lit(c.before)}")
    # Excluded only when every clause is known to hold; an unparseable date
    # keeps the row in scope, where a missing target row will surface it.
    return f"NOT COALESCE({' AND '.join(clauses)}, FALSE)"


def _expected(f: FieldSpec) -> tuple[str, str]:
    """(expected value, unmapped flag) for one mapped field of a source row."""
    raw = norm(ident(f.source))
    if f.transform == "date":
        return _date(raw, f.format or "%Y-%m-%d"), "FALSE"
    if f.transform == "money":
        return _money(raw), "FALSE"
    if f.transform == "map":
        if not f.value_map:
            return "CAST(NULL AS VARCHAR)", f"{raw} IS NOT NULL"
        whens = " ".join(f"WHEN {lit(k)} THEN {lit(v)}" for k, v in f.value_map.items())
        codes = ", ".join(lit(k) for k in f.value_map)
        return f"CASE {raw} {whens} END", f"({raw} IS NOT NULL AND {raw} NOT IN ({codes}))"
    return raw, "FALSE"  # text, parent: the legacy value itself


def _build_views(m: Migration) -> None:
    con, spec = m.con, m.spec
    con.execute("CREATE TABLE register (check_id VARCHAR, entity VARCHAR, key VARCHAR)")
    if m.register:
        con.executemany(
            "INSERT INTO register VALUES (?, ?, ?)",
            [(r.check, r.entity, r.key) for r in m.register],
        )

    for e in spec.entities:
        src, tgt = f"src_{e.name}", f"tgt_{e.name}"
        if src in m.present:
            key = norm(ident(e.source_key))
            cols = []
            for f in e.fields:
                value, unmapped = _expected(f)
                cols += [
                    f"{value} AS {ident(f.target)}",
                    f"{norm(ident(f.source))} AS {ident(f.target + '__src')}",
                    f"{unmapped} AS {ident(f.target + '__unmapped')}",
                ]
            scope = _in_scope(e)
            deferred = (
                f"{key} IN (SELECT key FROM register WHERE check_id = 'R3' "
                f"AND entity = {lit(e.name)})"
            )
            con.execute(
                f"CREATE VIEW exp_{e.name} AS SELECT _row, {key} AS _key, {scope} AS _in_scope, "
                f"({scope}) AND COALESCE({deferred}, FALSE) AS _deferred, {', '.join(cols)} "
                f"FROM {src}"
            )

        has_act = tgt in m.present and all(
            f"tgt_{f.parent}" in m.present for f in e.fields if f.transform == "parent"
        )
        if has_act:
            cols, joins = [], []
            for i, f in enumerate(e.fields):
                raw = norm(f"t.{ident(f.target)}")
                if f.transform == "date":
                    value = _date(raw, spec.target_date_format)
                elif f.transform == "money":
                    value = _money(raw)
                elif f.transform == "parent":
                    p = spec.entity(f.parent)
                    alias = f"p{i}"
                    # A parent id that appears more than once resolves to nothing.
                    joins.append(
                        f"LEFT JOIN (SELECT {norm(ident(p.target_id))} AS id, "
                        f"CASE WHEN count(*) = 1 THEN min({norm(ident(p.target_key))}) END AS lk "
                        f"FROM tgt_{p.name} GROUP BY 1) {alias} ON {alias}.id = {raw}"
                    )
                    value = f"{alias}.lk"
                else:
                    value = raw
                cols += [f"{value} AS {ident(f.target)}", f"{raw} AS {ident(f.target + '__raw')}"]
            con.execute(
                f"CREATE VIEW act_{e.name} AS SELECT t._row, {norm('t.' + ident(e.target_key))} "
                f"AS _key, {', '.join(cols)} FROM {tgt} t {' '.join(joins)}"
            )

        if src in m.present and has_act:
            con.execute(
                f"""CREATE VIEW pairs_{e.name} AS
                WITH s AS (SELECT _key FROM exp_{e.name} WHERE _in_scope AND _key IS NOT NULL
                           GROUP BY _key HAVING count(*) = 1),
                     t AS (SELECT _key FROM act_{e.name} WHERE _key IS NOT NULL
                           GROUP BY _key HAVING count(*) = 1)
                SELECT x._key, x._row AS source_row, a._row AS target_row
                FROM exp_{e.name} x JOIN s ON s._key = x._key
                JOIN act_{e.name} a ON a._key = x._key JOIN t ON t._key = a._key
                WHERE x._in_scope"""
            )


def load_migration(
    folder: str | Path,
    spec: Spec | None = None,
    exceptions: str | Path | None = None,
) -> Migration:
    """Load the four exports named in the spec from ``folder``.

    A missing file is not an error: the checks that need it return SKIP. The
    exception register defaults to ``folder/exceptions.csv`` when present.
    """
    folder = Path(folder)
    spec = spec or load_spec(DEFAULT_SPEC)
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 1")
    con.execute("SET preserve_insertion_order = true")

    reg_path = Path(exceptions) if exceptions else folder / "exceptions.csv"
    register = read_register(reg_path) if reg_path.exists() else []
    m = Migration(con=con, spec=spec, register=register)

    for e in spec.entities:
        for side, name in (("src", e.source_file), ("tgt", e.target_file)):
            path, table = folder / name, f"{side}_{e.name}"
            if not path.exists():
                m.problems[table] = f"{name} not found"
                continue
            with path.open(newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh), [])
            lacking = [c for c in dict.fromkeys(_required_columns(e, side)) if c not in header]
            if lacking:
                m.problems[table] = f"{name} lacks column(s) {', '.join(lacking)}"
                continue
            _load_csv(con, table, path, header)
            m.present.add(table)
    _build_views(m)
    return m
