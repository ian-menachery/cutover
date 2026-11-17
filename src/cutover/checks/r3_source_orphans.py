"""R3 source_orphans: in-scope legacy keys with no target row (dropped records)."""

from cutover.migration import Migration
from cutover.models import BLOCKER, Finding

from .base import Check, both_sides

ID, NAME = "R3", "source_orphans"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        rows = m.rows(
            f"""WITH s AS (SELECT _key FROM exp_{e.name} WHERE _in_scope AND _key IS NOT NULL
                       GROUP BY _key HAVING count(*) = 1)
            SELECT x._row, x._key FROM exp_{e.name} x JOIN s ON s._key = x._key
            WHERE x._in_scope
              AND x._key NOT IN (SELECT _key FROM act_{e.name} WHERE _key IS NOT NULL)
            ORDER BY x._row"""
        )
        out += [
            Finding(
                check=ID,
                severity=BLOCKER,
                entity=e.name,
                kind="missing_in_target",
                key=r["_key"],
                source_row=r["_row"],
                message=f"{e.name} {r['_key']} (legacy row {r['_row']}) has no row in the target.",
            )
            for r in rows
        ]
    return out


CHECK = Check(ID, NAME, run, both_sides)
