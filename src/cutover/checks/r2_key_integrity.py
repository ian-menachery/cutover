"""R2 key_integrity: blank or duplicate keys on either side.

Source-side problems are legacy data quality (warning); target-side ones mean
the load itself is wrong (blocker). Rows flagged here are kept out of matching.
"""

from cutover.migration import Migration
from cutover.models import BLOCKER, WARNING, Finding

from .base import Check, both_sides

ID, NAME = "R2", "key_integrity"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        sides = (
            ("source", f"exp_{e.name}", "WHERE _in_scope", WARNING, e.source_key),
            ("target", f"act_{e.name}", "", BLOCKER, e.target_key),
        )
        for side, view, where, severity, column in sides:
            rows = m.rows(
                f"""WITH r AS (SELECT _row, _key FROM {view} {where}),
                c AS (SELECT _key, count(*) AS n FROM r WHERE _key IS NOT NULL GROUP BY _key)
                SELECT r._row, r._key, c.n FROM r LEFT JOIN c ON c._key = r._key
                WHERE r._key IS NULL OR c.n > 1 ORDER BY r._row"""
            )
            for r in rows:
                rowref = {"source_row" if side == "source" else "target_row": r["_row"]}
                if r["_key"] is None:
                    out.append(
                        Finding(
                            check=ID,
                            severity=severity,
                            entity=e.name,
                            kind="blank_key",
                            message=f"{side} {e.name} row {r['_row']}: blank {column}.",
                            **rowref,
                        )
                    )
                else:
                    out.append(
                        Finding(
                            check=ID,
                            severity=severity,
                            entity=e.name,
                            kind="duplicate_key",
                            key=r["_key"],
                            message=(
                                f"{side} {e.name} {column} {r['_key']} appears {r['n']} times "
                                f"(row {r['_row']})."
                            ),
                            **rowref,
                        )
                    )
    return out


CHECK = Check(ID, NAME, run, both_sides)
