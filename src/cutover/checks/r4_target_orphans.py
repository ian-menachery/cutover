"""R4 target_orphans: target rows whose cross-reference matches no in-scope legacy key."""

from cutover.migration import Migration
from cutover.models import BLOCKER, Finding

from .base import Check, both_sides

ID, NAME = "R4", "target_orphans"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        rows = m.rows(
            f"""WITH t AS (SELECT _key FROM act_{e.name} WHERE _key IS NOT NULL
                       GROUP BY _key HAVING count(*) = 1)
            SELECT a._row, a._key,
                   a._key IN (SELECT _key FROM exp_{e.name} WHERE _key IS NOT NULL) AS known
            FROM act_{e.name} a JOIN t ON t._key = a._key
            WHERE a._key NOT IN
                  (SELECT _key FROM exp_{e.name} WHERE _in_scope AND _key IS NOT NULL)
            ORDER BY a._row"""
        )
        for r in rows:
            where = f"{e.name} {r['_key']} (target row {r['_row']})"
            out.append(
                Finding(
                    check=ID,
                    severity=BLOCKER,
                    entity=e.name,
                    kind="out_of_scope" if r["known"] else "not_in_source",
                    key=r["_key"],
                    target_row=r["_row"],
                    message=(
                        f"{where} matches a legacy row the scope rule excludes."
                        if r["known"]
                        else f"{where} matches no legacy row."
                    ),
                )
            )
    return out


CHECK = Check(ID, NAME, run, both_sides)
