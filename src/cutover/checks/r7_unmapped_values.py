"""R7 unmapped_values: picklist codes the value map lacks, and target values it does not allow.

Legacy side: in-scope rows whose code has no entry in the value map. Target
side: values outside the map's labels, or blank where the field is required.
"""

from cutover.migration import Migration, ident, lit
from cutover.models import BLOCKER, Finding

from .base import Check, both_sides

ID, NAME = "R7", "unmapped_values"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        for f in e.fields:
            if f.transform != "map":
                continue
            src, unm, raw = (ident(f.target + s) for s in ("__src", "__unmapped", "__raw"))
            for r in m.rows(
                f"SELECT _row, _key, {src} AS code FROM exp_{e.name} "
                f"WHERE _in_scope AND {unm} ORDER BY _row"
            ):
                out.append(
                    Finding(
                        check=ID,
                        severity=BLOCKER,
                        entity=e.name,
                        kind="unmapped_source_value",
                        key=r["_key"],
                        source_row=r["_row"],
                        field=f.target,
                        source_value=r["code"],
                        message=(
                            f"{e.name} {r['_key']}: legacy {f.source} {r['code']} has no "
                            f"mapping to {f.target}."
                        ),
                    )
                )
            labels = ", ".join(lit(v) for v in dict.fromkeys(f.value_map.values()))
            invalid = f"{raw} NOT IN ({labels})" if labels else "TRUE"
            required = "TRUE" if f.required else "FALSE"
            for r in m.rows(
                f"SELECT _row, _key, {raw} AS v FROM act_{e.name} "
                f"WHERE ({raw} IS NOT NULL AND {invalid}) OR ({raw} IS NULL AND {required}) "
                f"ORDER BY _row"
            ):
                where = f"{e.name} row {r['_row']} ({r['_key'] or 'no key'})"
                out.append(
                    Finding(
                        check=ID,
                        severity=BLOCKER,
                        entity=e.name,
                        kind="blank_required_value" if r["v"] is None else "invalid_target_value",
                        key=r["_key"],
                        target_row=r["_row"],
                        field=f.target,
                        found=r["v"],
                        message=(
                            f"{where}: {f.target} is blank but required."
                            if r["v"] is None
                            else f"{where}: {f.target} {r['v']} is not an allowed value."
                        ),
                    )
                )
    return out


CHECK = Check(ID, NAME, run, both_sides)
