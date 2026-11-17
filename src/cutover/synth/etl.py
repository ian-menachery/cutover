"""A correct migration, written in plain Python.

This is deliberately separate code from the checker: the checker derives what
the target should hold in DuckDB SQL from the spec; this produces the target
directly. If the two disagree on a clean run, Gate 1 says so.
"""

from datetime import date, datetime
from decimal import Decimal

from cutover.spec import Spec

SCOPE_CUTOFF = date(2019, 1, 1)  # the spec's scope rule: LP lapsed before this is not migrated


def _iso(legacy: str) -> str:
    return datetime.strptime(legacy, "%m/%d/%Y").strftime("%Y-%m-%d")


def _money(legacy: str) -> str:
    return f"{Decimal(legacy.replace(',', '')):.2f}"


def migrated(policy: dict[str, str]) -> bool:
    if policy["STATUS"] == "PN":  # deferred: manual migration after go-live
        return False
    if policy["STATUS"] == "LP":
        return datetime.strptime(policy["LAPSE_DT"], "%m/%d/%Y").date() >= SCOPE_CUTOFF
    return True


def migrate(legacy: dict[str, list[dict[str, str]]], spec: Spec) -> dict[str, list[dict]]:
    acc_map = {f.target: f.value_map for f in spec.entity("accounts").fields}
    pol_map = {f.target: f.value_map for f in spec.entity("policies").fields}

    accounts, ids = [], {}
    for n, a in enumerate(legacy["accounts"], start=1):
        ids[a["CUST_NO"]] = f"ACC-{n:06d}"
        accounts.append(
            {
                "account_id": ids[a["CUST_NO"]],
                "legacy_cust_no": a["CUST_NO"],
                "account_name": a["CUST_NAME"].strip(),
                "account_type": acc_map["account_type"][a["CUST_TYPE"]],
                "state": a["ST"],
                "opened_on": _iso(a["OPEN_DT"]),
                "status": acc_map["status"][a["STATUS"]],
                "created_by": "MIGRATION",
            }
        )

    policies = []
    for p in legacy["policies"]:
        if not migrated(p):
            continue
        policies.append(
            {
                "policy_id": f"POL-{len(policies) + 1:07d}",
                "legacy_pol_no": p["POL_NO"],
                "account_id": ids[p["CUST_NO"]],
                "product": pol_map["product"][p["PLAN_CD"]],
                "billing_mode": pol_map["billing_mode"][p["MODE"]],
                "annual_premium": _money(p["ANN_PREM"]),
                "face_amount": _money(p["FACE_AMT"]),
                "issue_date": _iso(p["ISSUE_DT"]),
                "status": pol_map["status"][p["STATUS"]],
                "created_by": "MIGRATION",
            }
        )
    return {"accounts": accounts, "policies": policies}
