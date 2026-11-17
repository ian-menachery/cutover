"""The nine injected defects, each a list of patch operations on the clean data.

Every defect is generated against the same clean base with its own seeded
stream, so any subset composes to the same rows whichever others are on.
Row-level defects (drop, duplicate, lost cross-reference, extras) claim their
rows first; field-level defects then use only unclaimed rows, so each recorded
instance has one cause. An instance is recorded only if the patch changed a
value.

Ops: ``delete`` and ``set`` address a row by id (target: the target id;
source: the legacy key); ``append`` adds a row at the end.
"""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

SCALES = {
    "gate": {
        "accounts": 1500,
        "D1p": 12,
        "D1a": 2,
        "D2": 5,
        "D4": 6,
        "D7": 8,
        "D8a": 3,
        "D8p": 5,
        "D9": 6,
    },
    "demo": {
        "accounts": 300,
        "D1p": 4,
        "D1a": 1,
        "D2": 2,
        "D4": 3,
        "D7": 3,
        "D8a": 2,
        "D8p": 3,
        "D9": 4,
    },
}
UNMAPPED_CODES = ("TL15", "GUL")
NAME_LIMIT = 30
BATCH = (0.40, 0.52)  # the load batch D5 hits, as a slice of target policies in load order


@dataclass
class Defect:
    id: str
    title: str
    description: str
    ops: list[dict] = field(default_factory=list)
    instances: list[dict] = field(default_factory=list)

    def op(self, op: str, side: str, entity: str, **kw) -> None:
        self.ops.append({"op": op, "side": side, "entity": entity, **kw})

    def hit(self, entity: str, key: str, field: str | None = None, target_id: str | None = None):
        self.instances.append(
            {"entity": entity, "key": key, "field": field, "target_id": target_id}
        )


def make_defects(legacy: dict, target: dict, seed: int, scale: str) -> list[Defect]:
    c = SCALES[scale]
    rng = random.Random(seed * 7919 + 17)
    accounts, policies = target["accounts"], target["policies"]
    by_account = defaultdict(list)
    for p in policies:
        by_account[p["account_id"]].append(p)
    legacy_pol = {p["POL_NO"]: p for p in legacy["policies"]}
    pending = {p["CUST_NO"] for p in legacy["policies"] if p["STATUS"] == "PN"}
    used_acc: set[str] = set()  # account_ids claimed by row-level defects
    used_pol: set[str] = set()  # policy_ids claimed by row-level defects

    def free_policies():
        return [p for p in policies if p["policy_id"] not in used_pol]

    # D1 dropped records: whole accounts with their policies, then single policies.
    d1 = Defect("D1", "Dropped records", "")
    cands = [
        a for a in accounts if a["legacy_cust_no"] not in pending and by_account[a["account_id"]]
    ]
    for a in rng.sample(cands, c["D1a"]):
        used_acc.add(a["account_id"])
        d1.op("delete", "target", "accounts", id=a["account_id"])
        d1.hit("accounts", a["legacy_cust_no"])
        for p in by_account[a["account_id"]]:
            used_pol.add(p["policy_id"])
            d1.op("delete", "target", "policies", id=p["policy_id"])
            d1.hit("policies", p["legacy_pol_no"])
    for p in rng.sample(free_policies(), c["D1p"]):
        used_pol.add(p["policy_id"])
        d1.op("delete", "target", "policies", id=p["policy_id"])
        d1.hit("policies", p["legacy_pol_no"])
    n_pol = sum(i["entity"] == "policies" for i in d1.instances)
    d1.description = (
        f"{n_pol} policies and {c['D1a']} account(s) never loaded; the dropped account(s) "
        "took their policies with them."
    )

    # D2 duplicated accounts: loaded a second time under new ids.
    d2 = Defect("D2", "Duplicated accounts", f"{c['D2']} accounts loaded twice under new ids.")
    free_acc = [a for a in accounts if a["account_id"] not in used_acc]
    for i, a in enumerate(rng.sample(free_acc, c["D2"]), start=1):
        used_acc.add(a["account_id"])
        d2.op(
            "append", "target", "accounts", row={**a, "account_id": f"ACC-{len(accounts) + i:06d}"}
        )
        d2.hit("accounts", a["legacy_cust_no"])

    # D7 lost cross-reference: the legacy policy number did not carry over.
    d7 = Defect(
        "D7",
        "Lost cross-reference",
        f"{c['D7']} policies loaded with a blank legacy policy number.",
    )
    for p in rng.sample(free_policies(), c["D7"]):
        used_pol.add(p["policy_id"])
        d7.op("set", "target", "policies", id=p["policy_id"], field="legacy_pol_no", value="")
        d7.hit("policies", p["legacy_pol_no"], target_id=p["policy_id"])

    # D8 test records left in the target after UAT.
    d8 = Defect(
        "D8",
        "Test records left in",
        f"{c['D8a']} test accounts and {c['D8p']} test policies from UAT were never deleted.",
    )
    test_ids = []
    for i in range(1, c["D8a"] + 1):
        aid, key = f"ACC-{len(accounts) + c['D2'] + i:06d}", f"9999{i:04d}"
        test_ids.append(aid)
        d8.op(
            "append",
            "target",
            "accounts",
            row={
                "account_id": aid,
                "legacy_cust_no": key,
                "account_name": f"ZZ TEST ACCOUNT {i}",
                "account_type": "Individual",
                "state": "MA",
                "opened_on": "2026-10-15",
                "status": "Active",
                "created_by": "uat.tester",
            },
        )
        d8.hit("accounts", key, target_id=aid)
    for i in range(1, c["D8p"] + 1):
        pid, key = f"POL-{len(policies) + i:07d}", f"P999{i:06d}"
        d8.op(
            "append",
            "target",
            "policies",
            row={
                "policy_id": pid,
                "legacy_pol_no": key,
                "account_id": test_ids[(i - 1) % len(test_ids)],
                "product": rng.choice(("Term 10", "Term 20", "Whole Life")),
                "billing_mode": rng.choice(("Annual", "Monthly")),
                "annual_premium": f"{rng.randint(100, 900)}.00",
                "face_amount": "100000.00",
                "issue_date": "2026-10-15",
                "status": "In force",
                "created_by": "uat.tester",
            },
        )
        d8.hit("policies", key, target_id=pid)

    # D9 broken parent links: half to the wrong account, half to no account.
    d9 = Defect(
        "D9", "Broken parent links", f"{c['D9']} policies point at the wrong account or at none."
    )
    linkable = [a["account_id"] for a in accounts if a["account_id"] not in used_acc]
    for i, p in enumerate(rng.sample(free_policies(), c["D9"])):
        if i < c["D9"] // 2:
            wrong = rng.choice([a for a in linkable if a != p["account_id"]])
        else:
            wrong = f"ACC-{999_000 + i:06d}"
        d9.op("set", "target", "policies", id=p["policy_id"], field="account_id", value=wrong)
        d9.hit("policies", p["legacy_pol_no"], "account_id")

    # D4 unmapped picklist values: legacy codes the value map never covered.
    d4 = Defect(
        "D4",
        "Unmapped plan codes",
        f"{c['D4']} legacy policies carry plan codes {' and '.join(UNMAPPED_CODES)}, which the "
        "value map lacks; they loaded with a blank product.",
    )
    for i, p in enumerate(rng.sample(free_policies(), c["D4"])):
        code = UNMAPPED_CODES[i % len(UNMAPPED_CODES)]
        d4.op("set", "source", "policies", id=p["legacy_pol_no"], field="PLAN_CD", value=code)
        d4.op("set", "target", "policies", id=p["policy_id"], field="product", value="")
        d4.hit("policies", p["legacy_pol_no"], "product")

    # D3 doubled amounts: the semi-annual branch of the premium mapping multiplied by 2.
    d3 = Defect(
        "D3",
        "Doubled premium",
        "Mapping bug: every semi-annual policy's annual premium was multiplied by 2.",
    )
    for p in free_policies():
        if p["billing_mode"] == "Semi-annual":
            doubled = f"{Decimal(p['annual_premium']) * 2:.2f}"
            d3.op(
                "set",
                "target",
                "policies",
                id=p["policy_id"],
                field="annual_premium",
                value=doubled,
            )
            d3.hit("policies", p["legacy_pol_no"], "annual_premium")

    # D5 date-format shift: one batch read MM/DD/YYYY as DD/MM/YYYY.
    d5 = Defect(
        "D5",
        "Date-format shift",
        "One load batch read issue dates as DD/MM: day and month swapped where the day is 12 or "
        "less, blank where it is more.",
    )
    lo, hi = (int(len(policies) * b) for b in BATCH)
    for p in policies[lo:hi]:
        if p["policy_id"] in used_pol:
            continue
        mm, dd, yyyy = (int(x) for x in legacy_pol[p["legacy_pol_no"]]["ISSUE_DT"].split("/"))
        if dd == mm:
            continue  # reads the same either way: not a defect
        value = date(yyyy, dd, mm).isoformat() if dd <= 12 else ""
        d5.op("set", "target", "policies", id=p["policy_id"], field="issue_date", value=value)
        d5.hit("policies", p["legacy_pol_no"], "issue_date")

    # D6 truncated text: the target name field was sized at 30 characters.
    d6 = Defect(
        "D6",
        "Truncated names",
        f"Account names longer than {NAME_LIMIT} characters were cut at {NAME_LIMIT}.",
    )
    for a in accounts:
        if a["account_id"] not in used_acc and len(a["account_name"]) > NAME_LIMIT:
            cut = a["account_name"][:NAME_LIMIT]
            d6.op("set", "target", "accounts", id=a["account_id"], field="account_name", value=cut)
            d6.hit("accounts", a["legacy_cust_no"], "account_name")

    return sorted([d1, d2, d3, d4, d5, d6, d7, d8, d9], key=lambda d: int(d.id[1:]))
