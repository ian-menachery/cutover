"""R8 referential_integrity: target rows whose parent link matches no target parent row."""

from cutover.migration import Migration, ident, norm
from cutover.models import BLOCKER, Finding

from .base import Check, blank, target_side

ID, NAME = "R8", "referential_integrity"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        for f in e.fields:
            if f.transform != "parent":
                continue
            p = m.spec.entity(f.parent)
            pid = norm(ident(p.target_id))
            raw = ident(f.target + "__raw")
            for r in m.rows(
                f"""SELECT _row, _key, {raw} AS v FROM act_{e.name}
                WHERE {raw} IS NULL
                   OR {raw} NOT IN (SELECT {pid} FROM tgt_{p.name} WHERE {pid} IS NOT NULL)
                ORDER BY _row"""
            ):
                out.append(
                    Finding(
                        check=ID,
                        severity=BLOCKER,
                        entity=e.name,
                        kind="dangling_parent",
                        key=r["_key"],
                        target_row=r["_row"],
                        field=f.target,
                        found=r["v"],
                        message=(
                            f"{e.name} row {r['_row']} ({r['_key'] or 'no key'}): {f.target} "
                            f"{blank(r['v'])} matches no {p.name} row."
                        ),
                    )
                )
    return out


CHECK = Check(ID, NAME, run, target_side)
