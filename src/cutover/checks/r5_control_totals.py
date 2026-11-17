"""R5 control_totals: count and money sums by group, expected vs target, to the cent.

The expected side is the in-scope legacy rows less registered deferrals, each
grouped by the label the spec maps it to. A code the value map lacks groups as
UNMAPPED(<code>): the spec implies no label for it, so it cannot share a group
with a blank target value.
"""

from cutover.migration import Migration, ident
from cutover.models import BLOCKER, Finding

from .base import Check, blank, both_sides

ID, NAME = "R5", "control_totals"
ZERO = "CAST(0 AS DECIMAL(38,2))"


def run(m: Migration) -> list[Finding]:
    out = []
    for e in m.spec.entities:
        if not e.group_by:
            continue
        exp_groups, act_groups = [], []
        for i, g in enumerate(e.group_by):
            f, col = e.field(g), ident(g)
            if f.transform == "map":
                unmapped = f"'UNMAPPED(' || {ident(g + '__src')} || ')'"
                exp_groups.append(
                    f"COALESCE({col}, CASE WHEN {ident(g + '__unmapped')} THEN {unmapped} END) "
                    f"AS g{i}"
                )
            else:
                exp_groups.append(f"CAST({col} AS VARCHAR) AS g{i}")
            act_groups.append(f"CAST({col} AS VARCHAR) AS g{i}")
        sums = [f"SUM({ident(s)}) AS s{j}" for j, s in enumerate(e.sums)]
        on = " AND ".join(f"x.g{i} IS NOT DISTINCT FROM a.g{i}" for i in range(len(e.group_by)))
        pick = [f"COALESCE(x.g{i}, a.g{i}) AS g{i}" for i in range(len(e.group_by))]
        pick += ["COALESCE(x.n, 0) AS xn", "COALESCE(a.n, 0) AS an"]
        for j in range(len(e.sums)):
            pick += [f"COALESCE(x.s{j}, {ZERO}) AS xs{j}", f"COALESCE(a.s{j}, {ZERO}) AS as{j}"]
        order = ", ".join(f"g{i} NULLS FIRST" for i in range(len(e.group_by)))
        rows = m.rows(
            f"""WITH x AS (SELECT {", ".join(exp_groups + ["count(*) AS n"] + sums)}
                       FROM exp_{e.name} WHERE _in_scope AND NOT _deferred GROUP BY ALL),
                 a AS (SELECT {", ".join(act_groups + ["count(*) AS n"] + sums)}
                       FROM act_{e.name} GROUP BY ALL)
            SELECT {", ".join(pick)} FROM x FULL OUTER JOIN a ON {on} ORDER BY {order}"""
        )
        for r in rows:
            group = {g: r[f"g{i}"] for i, g in enumerate(e.group_by)}
            label = ", ".join(f"{k}={blank(v)}" for k, v in group.items())
            measures = [("count", r["xn"], r["an"])]
            measures += [(s, r[f"xs{j}"], r[f"as{j}"]) for j, s in enumerate(e.sums)]
            for measure, expected, found in measures:
                if expected == found:
                    continue
                out.append(
                    Finding(
                        check=ID,
                        severity=BLOCKER,
                        entity=e.name,
                        kind="control_total_mismatch",
                        field=measure,
                        group=group,
                        expected=str(expected),
                        found=str(found),
                        message=(
                            f"{e.name} [{label}] {measure}: expected {expected}, found {found} "
                            f"(difference {found - expected})."
                        ),
                    )
                )
    return out


CHECK = Check(ID, NAME, run, both_sides)
