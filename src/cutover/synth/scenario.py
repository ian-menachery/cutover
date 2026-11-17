"""Build a scenario: clean base + chosen defects, written as the four exports.

``compose`` is the reference for the site's TypeScript composer: defects apply
in D1..D9 order, ops in list order, appends at the end of the table.
"""

import copy
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from cutover.spec import DEFAULT_SPEC, Spec, load_spec
from cutover.synth.base import make_legacy
from cutover.synth.defects import SCALES, Defect, make_defects
from cutover.synth.etl import migrate, migrated

SOURCE_COLUMNS = {
    "accounts": ["CUST_NO", "CUST_NAME", "CUST_TYPE", "ST", "OPEN_DT", "STATUS"],
    "policies": [
        "POL_NO",
        "CUST_NO",
        "PLAN_CD",
        "MODE",
        "ANN_PREM",
        "FACE_AMT",
        "ISSUE_DT",
        "STATUS",
        "LAPSE_DT",
    ],
}
TARGET_COLUMNS = {
    "accounts": [
        "account_id",
        "legacy_cust_no",
        "account_name",
        "account_type",
        "state",
        "opened_on",
        "status",
        "created_by",
    ],
    "policies": [
        "policy_id",
        "legacy_pol_no",
        "account_id",
        "product",
        "billing_mode",
        "annual_premium",
        "face_amount",
        "issue_date",
        "status",
        "created_by",
    ],
}
REGISTER_COLUMNS = ["check", "entity", "key", "reason", "ticket"]


@dataclass
class Built:
    spec: Spec
    tables: dict  # {"source": {entity: rows}, "target": {entity: rows}}
    defects: list[Defect]
    register: list[dict]


def build(seed: int, scale: str = "gate") -> Built:
    spec = load_spec(DEFAULT_SPEC)
    legacy = make_legacy(seed, SCALES[scale]["accounts"])
    target = migrate(legacy, spec)
    register = [
        {
            "check": "R3",
            "entity": "policies",
            "key": p["POL_NO"],
            "reason": "Pending policy; migrated manually after go-live",
            "ticket": "MIG-142",
        }
        for p in legacy["policies"]
        if p["STATUS"] == "PN"
    ]
    defects = make_defects(legacy, target, seed, scale)
    return Built(spec, {"source": legacy, "target": target}, defects, register)


def compose(built: Built, enabled: set[str]) -> dict:
    tables = copy.deepcopy(built.tables)
    for d in built.defects:
        if d.id not in enabled:
            continue
        for op in d.ops:
            e = built.spec.entity(op["entity"])
            rows = tables[op["side"]][op["entity"]]
            if op["op"] == "append":
                rows.append(dict(op["row"]))
                continue
            id_col = e.target_id if op["side"] == "target" else e.source_key
            i = next((i for i, r in enumerate(rows) if r[id_col] == op["id"]), None)
            if i is None:
                raise KeyError(f"{d.id}: no {op['side']} {op['entity']} row {op['id']}")
            if op["op"] == "delete":
                del rows[i]
            else:
                rows[i][op["field"]] = op["value"]
    return tables


def _expected_group(spec: Spec, src: dict) -> list:
    pol = spec.entity("policies")
    out = []
    for g in pol.group_by:
        f = pol.field(g)
        code = src[f.source]
        out.append(f.value_map.get(code, f"UNMAPPED({code})"))
    return out


def answer_key(built: Built, tables: dict, enabled: set[str]) -> dict:
    """Instances with their final target row and the control-total groups they touch."""
    spec = built.spec
    src_pol = {p["POL_NO"]: p for p in tables["source"]["policies"]}
    rows = {
        e: {r[spec.entity(e).target_id]: (n, r) for n, r in enumerate(tables["target"][e], start=2)}
        for e in tables["target"]
    }
    pol = spec.entity("policies")
    src_keys = {e.name: [r[e.source_key] for r in tables["source"][e.name]] for e in spec.entities}
    tgt_keys = {e.name: [r[e.target_key] for r in tables["target"][e.name]] for e in spec.entities}
    by_legacy = {r["legacy_pol_no"]: r for r in tables["target"]["policies"]}
    instances = []
    for d in built.defects:
        if d.id not in enabled:
            continue
        for inst in d.instances:
            ent, k = inst["entity"], inst["key"]
            target_row = None
            if inst["target_id"] and inst["target_id"] in rows[ent]:
                target_row = rows[ent][inst["target_id"]][0]
            # A row present on one side only, or loaded twice, moves the record count.
            one_side = (k in src_keys[ent]) != (k in tgt_keys[ent] or target_row is not None)
            moves_count = inst["field"] is None and (one_side or tgt_keys[ent].count(k) > 1)
            groups = []
            totals_field = inst["field"] in (*pol.group_by, *pol.sums)
            if ent == "policies" and ((inst["field"] is None and one_side) or totals_field):
                src = src_pol.get(k)
                if src and migrated(src):
                    groups.append(_expected_group(spec, src))
                if inst["target_id"]:
                    tgt = rows["policies"].get(inst["target_id"], (None, None))[1]
                else:
                    tgt = by_legacy.get(k)
                if tgt:
                    groups.append([tgt[g] or None for g in pol.group_by])
            instances.append(
                {
                    "defect": d.id,
                    "entity": ent,
                    "key": k,
                    "target_row": target_row,
                    "field": inst["field"],
                    "moves_count": moves_count,
                    "groups": groups,
                }
            )
    return {"defects": sorted(enabled, key=lambda x: int(x[1:])), "instances": instances}


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in rows)


def write_tables(out: Path, spec: Spec, tables: dict, register: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for e in spec.entities:
        _write_csv(out / e.source_file, SOURCE_COLUMNS[e.name], tables["source"][e.name])
        _write_csv(out / e.target_file, TARGET_COLUMNS[e.name], tables["target"][e.name])
    _write_csv(out / "exceptions.csv", REGISTER_COLUMNS, register)


def write_scenario(
    out: str | Path, seed: int, scale: str = "gate", defects: list[str] | None = None
) -> dict:
    """Write one scenario. ``defects=None`` means all nine; ``[]`` means clean."""
    out = Path(out)
    built = build(seed, scale)
    enabled = {d.id for d in built.defects} if defects is None else set(defects)
    tables = compose(built, enabled)
    write_tables(out, built.spec, tables, built.register)
    key = answer_key(built, tables, enabled)
    (out / "answer_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    return key
