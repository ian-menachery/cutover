"""R1 record_counts: in-scope legacy rows, less registered deferrals, vs target rows."""

from cutover.migration import Migration
from cutover.models import BLOCKER, Finding

from .base import Check, both_sides

ID, NAME = "R1", "record_counts"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        expected = m.scalar(f"SELECT count(*) FROM exp_{e.name} WHERE _in_scope AND NOT _deferred")
        deferred = m.scalar(f"SELECT count(*) FROM exp_{e.name} WHERE _deferred")
        found = m.scalar(f"SELECT count(*) FROM tgt_{e.name}")
        if expected != found:
            out.append(
                Finding(
                    check=ID,
                    severity=BLOCKER,
                    entity=e.name,
                    kind="count_mismatch",
                    expected=str(expected),
                    found=str(found),
                    message=(
                        f"{e.name}: expected {expected} target rows (in-scope legacy rows "
                        f"less {deferred} deferred), found {found}."
                    ),
                )
            )
    return out


CHECK = Check(ID, NAME, run, both_sides)
