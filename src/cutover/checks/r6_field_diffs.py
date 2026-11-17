"""R6 field_diffs: each mapped field of each matched pair, transformed legacy vs target.

Only keys that appear exactly once on each side are compared. A field whose
legacy code the value map lacks is left to R7. An unparseable value on either
side is a difference, never a silent match of two NULLs.
"""

from cutover.migration import Migration, ident
from cutover.models import BLOCKER, WARNING, Finding

from .base import Check, blank, both_sides, show

ID, NAME = "R6", "field_diffs"


def _message(entity: str, f, key: str, src, exp, raw, act) -> str:
    head = f"{entity} {key}: {f.target}"
    if exp is None and src is not None:
        return f"{head} legacy value {src} could not be parsed."
    if f.transform == "parent":
        if act is None:
            return f"{head} {blank(raw)} matches no {f.parent} row; expected legacy {exp}."
        return f"{head} {raw} belongs to legacy {act}, expected legacy {exp}."
    if act is None and raw is not None:
        return f"{head} target value {raw} could not be parsed; expected {blank(exp)}."
    return f"{head} expected {blank(exp)}, found {blank(raw)}."


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        hits = []
        for i, f in enumerate(e.fields):
            t = ident(f.target)
            src, unm, raw = (ident(f.target + s) for s in ("__src", "__unmapped", "__raw"))
            rows = m.rows(
                f"""SELECT p._key, p.source_row, p.target_row, x.{src} AS src,
                       CAST(x.{t} AS VARCHAR) AS exp, a.{raw} AS raw,
                       CAST(a.{t} AS VARCHAR) AS act
                FROM pairs_{e.name} p
                JOIN exp_{e.name} x ON x._row = p.source_row
                JOIN act_{e.name} a ON a._row = p.target_row
                WHERE NOT x.{unm} AND (x.{t} IS DISTINCT FROM a.{t}
                    OR (a.{t} IS NULL AND a.{raw} IS NOT NULL)
                    OR (x.{t} IS NULL AND x.{src} IS NOT NULL))"""
            )
            for r in rows:
                found = r["act"] if f.transform == "parent" else r["raw"]
                finding = Finding(
                    check=ID,
                    severity=WARNING if f.cls == "text" else BLOCKER,
                    entity=e.name,
                    kind="field_mismatch",
                    key=r["_key"],
                    source_row=r["source_row"],
                    target_row=r["target_row"],
                    field=f.target,
                    source_value=show(r["src"]),
                    expected=show(r["exp"]),
                    found=show(found),
                    message=_message(e.name, f, r["_key"], r["src"], r["exp"], r["raw"], r["act"]),
                )
                hits.append((r["source_row"], i, finding))
        out += [finding for _, _, finding in sorted(hits, key=lambda h: (h[0], h[1]))]
    return out


CHECK = Check(ID, NAME, run, both_sides)
