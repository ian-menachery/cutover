"""Inject defects into the clean migration in clean/ and write defected/ plus sealed/answer_key.json.

Python 3 stdlib only. Deterministic (fixed seed). Run from anywhere:
    py inject.py
"""
import csv
import datetime as dt
import json
import random
import shutil
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUT = ROOT / "defected"
SEALED = ROOT / "sealed"
SEED = 20261117


def read(name):
    with open(CLEAN / name, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        return r.fieldnames, [dict(row) for row in r]


def write(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow([row[h] for h in header])


def ldate(s):
    return dt.datetime.strptime(s, "%m/%d/%Y").date()


rng = random.Random(SEED)
spec = json.loads((CLEAN / "mapping.json").read_text(encoding="utf-8"))
pmaps = {f["source"]: f["transform"].get("map") for f in spec["entities"][1]["fields"]}

la_h, la = read("legacy_accounts.csv")
lp_h, lp = read("legacy_policies.csv")
ta_h, ta = read("target_accounts.csv")
tp_h, tp = read("target_policies.csv")

la_by = {r["CUST_NO"]: r for r in la}
lp_by = {r["POL_NO"]: r for r in lp}
lp_pos = {r["POL_NO"]: i for i, r in enumerate(lp)}
ta_by = {r["legacy_cust_no"]: r for r in ta}
acc_id_of = {r["legacy_cust_no"]: r["account_id"] for r in ta}
cust_of_acc = {r["account_id"]: r["legacy_cust_no"] for r in ta}
tp_by = {r["legacy_pol_no"]: r for r in tp}

defects = []
# planned instances; target_row is resolved after the files are assembled
plan = []  # dicts: defect, entity, key, ref (("acc"|"pol", obj id) or None), field
decoys = []
used_acc, used_pol = set(), set()


def defect(did, title, desc):
    defects.append({"id": did, "title": title, "description": desc})


def inst(did, entity, key, row, field):
    plan.append({"defect": did, "entity": entity, "key": key, "row": row, "field": field})


def take(cands, n, used):
    cands = sorted(c for c in cands if c not in used)
    pick = rng.sample(cands, n)
    used.update(pick)
    return sorted(pick)


cutoff = dt.date(2019, 1, 1)
oos = [r["POL_NO"] for r in lp if r["STATUS"] == "LP" and r["LAPSE_DT"] and ldate(r["LAPSE_DT"]) < cutoff]
excepted = {"P100059481", "P100280770", "P100342364", "P100738542"}
inscope_live = [r["legacy_pol_no"] for r in tp]  # migrated, in clean target
pol_count = defaultdict(int)
for r in tp:
    pol_count[r["account_id"]] += 1

# ---------------------------------------------------------------- policies: out-of-scope DI rows migrated
di_oos = sorted(k for k in oos if lp_by[k]["PLAN_CD"] == "DI")
used_pol.update(di_oos)
di_accts = {lp_by[k]["CUST_NO"] for k in di_oos}

# ---------------------------------------------------------------- accounts
nopol = [c for c in acc_id_of if pol_count[acc_id_of[c]] == 0 and c not in di_accts]
name_count = defaultdict(int)
for r in la:
    name_count[r["CUST_NAME"]] += 1
nopol = [c for c in nopol if name_count[la_by[c]["CUST_NAME"]] == 1]

defect("B1", "Account name not trimmed",
       "Legacy CUST_NAME carries surrounding blanks (fixed-width padding) and the load skipped the trim step, "
       "so target account_name keeps the padding; the spec's text transform requires it trimmed.")
b1 = take(la_by, 3, used_acc)
pads = [("", "   "), (" ", ""), ("  ", " ")]
for c, (lead, trail) in zip(b1, pads):
    la_by[c]["CUST_NAME"] = lead + la_by[c]["CUST_NAME"] + trail
    ta_by[c]["account_name"] = la_by[c]["CUST_NAME"]
    inst("B1", "accounts", c, ("acc", c), "account_name")

defect("B2", "Account name re-cased",
       "A name-cleansing rule converted some uppercase legacy names to proper case (e.g. SMITH, JOHN -> Smith, John). "
       "The text transform only trims; case must be preserved.")
indiv = [c for c in la_by if la_by[c]["CUST_TYPE"] == "I"]
for c in take(indiv, 6, used_acc):
    ta_by[c]["account_name"] = la_by[c]["CUST_NAME"].title()
    inst("B2", "accounts", c, ("acc", c), "account_name")

defect("B3", "Opened date day and month swapped",
       "A batch of accounts was parsed as DD/MM/YYYY instead of MM/DD/YYYY. Where the day is 12 or less the result "
       "is still a valid date, so opened_on parses fine but has day and month swapped.")
elig = [c for c in la_by if ldate(la_by[c]["OPEN_DT"]).day <= 12 and ldate(la_by[c]["OPEN_DT"]).day != ldate(la_by[c]["OPEN_DT"]).month]
for c in take(elig, 24, used_acc):
    d = ldate(la_by[c]["OPEN_DT"])
    ta_by[c]["opened_on"] = dt.date(d.year, d.day, d.month).isoformat()
    inst("B3", "accounts", c, ("acc", c), "opened_on")

defect("B4", "Account type valid but wrong",
       "Some trust accounts (CUST_TYPE T) were loaded as account_type Individual: a valid picklist label, wrong for the row.")
trusts = [c for c in la_by if la_by[c]["CUST_TYPE"] == "T"]
for c in take(trusts, 3, used_acc):
    ta_by[c]["account_type"] = "Individual"
    inst("B4", "accounts", c, ("acc", c), "account_type")

defect("B5", "Optional state dropped",
       "state was blanked on a few accounts whose legacy ST is populated. state is not required, but the spec maps it "
       "from ST, so a blank is a value discrepancy.")
for c in take(la_by, 4, used_acc):
    ta_by[c]["state"] = ""
    inst("B5", "accounts", c, ("acc", c), "state")

defect("B6", "Duplicate account rows",
       "A retried batch re-inserted some accounts: the same legacy_cust_no appears twice with a new account_id. "
       "The instance points at the second (appended) row.")
b6 = take(nopol, 2, used_acc)

defect("B7", "Account missing from target",
       "A legacy account has no target row. Accounts have no scope rule and no exception, so every account must migrate.")
b7 = take(nopol, 1, used_acc)

defect("B8", "Account re-keyed (cross-reference transposed)",
       "One account's legacy_cust_no was keyed with its last two digits transposed. The legacy account therefore has "
       "no target row (instance with target_row null) and the target row has no legacy counterpart (instance keyed by "
       "the bad cross-reference).")
b8 = take(nopol, 1, used_acc)
allc = set(la_by)
for c in b8:
    bad = c[:-2] + c[-1] + c[-2]
    assert bad != c and bad not in allc
    ta_by[c]["legacy_cust_no"] = bad
    inst("B8", "accounts", c, None, None)
    inst("B8", "accounts", bad, ("acc", c), None)

defect("B9", "Test account left in target",
       "A test account with a blank legacy_cust_no is in the target. It has no legacy counterpart (key null).")

# account decoys (spec-compliant, not defects): legacy padding that the target correctly trimmed
for c in take(la_by, 10, used_acc):
    la_by[c]["CUST_NAME"] = rng.choice([" ", "  ", ""]) + la_by[c]["CUST_NAME"] + rng.choice([" ", "   "])
    decoys.append({"entity": "accounts", "key": c, "field": "account_name",
                   "note": "legacy CUST_NAME padded; target correctly trimmed"})
for c in take(la_by, 5, used_acc):
    la_by[c]["ST"] = la_by[c]["ST"] + " "
    decoys.append({"entity": "accounts", "key": c, "field": "state",
                   "note": "legacy ST padded; target correctly trimmed"})

# ---------------------------------------------------------------- policies
defect("B10", "Out-of-scope lapsed policies migrated",
       "The scope filter (STATUS LP with LAPSE_DT before 2019-01-01) was not applied in the Disability Income extract, "
       "so every out-of-scope DI lapsed policy was migrated. Values are otherwise correctly transformed; the rows "
       "should not exist.")

defect("B11", "Partial load: block of policies missing",
       "A chunk of consecutive in-scope policies failed to load and was never retried; they have no target row.")
order = [r["legacy_pol_no"] for r in tp]
while True:
    s = rng.randrange(0, len(order) - 12)
    blk = order[s:s + 12]
    if not (set(blk) & used_pol):
        break
used_pol.update(blk)
b11 = blk

defect("B12", "Unregistered pending policy held back",
       "A fifth pending policy (legacy STATUS PN) was held back like the MIG-142 ones but never added to the exception "
       "register, so its absence from the target is not excused.")
ifs = [k for k in inscope_live if lp_by[k]["STATUS"] == "IF"]
b12 = take(ifs, 1, used_pol)
for k in b12:
    lp_by[k]["STATUS"] = "PN"

defect("B13", "Duplicate policy rows",
       "A retried batch re-inserted some policies with new policy_ids; the same legacy_pol_no appears twice. "
       "The instance points at the second (appended) row.")
b13 = take(inscope_live, 3, used_pol)

defect("B14", "Premium off by one cent, offsetting",
       "annual_premium is off by exactly 0.01 on pairs of policies in the same product x billing_mode group, one up "
       "and one down, so the signed-off control totals still tie.")
groups = defaultdict(list)
for k in inscope_live:
    r = tp_by[k]
    groups[(r["product"], r["billing_mode"])].append(k)
gnames = sorted(groups)
b14 = []
for _ in range(10):
    g = rng.choice(gnames)
    pair = take(groups[g], 2, used_pol)
    rng.shuffle(pair)
    for k, delta in zip(pair, (Decimal("0.01"), Decimal("-0.01"))):
        tp_by[k]["annual_premium"] = str(Decimal(tp_by[k]["annual_premium"]) + delta)
        b14.append(k)
for k in sorted(b14):
    inst("B14", "policies", k, ("pol", k), "annual_premium")

defect("B15", "Premiums cross-wired between adjacent policies",
       "Two pairs of adjacent policies in the same product x billing_mode group had their annual_premium values "
       "swapped. Each value is a real premium and the group totals tie, but each row carries its neighbour's premium.")
n = 0
cands = list(range(len(order) - 1))
rng.shuffle(cands)
for i in cands:
    a, b = order[i], order[i + 1]
    ra, rb = tp_by[a], tp_by[b]
    if a in used_pol or b in used_pol:
        continue
    if (ra["product"], ra["billing_mode"]) != (rb["product"], rb["billing_mode"]):
        continue
    if ra["annual_premium"] == rb["annual_premium"]:
        continue
    ra["annual_premium"], rb["annual_premium"] = rb["annual_premium"], ra["annual_premium"]
    used_pol.update((a, b))
    inst("B15", "policies", a, ("pol", a), "annual_premium")
    inst("B15", "policies", b, ("pol", b), "annual_premium")
    n += 1
    if n == 2:
        break

defect("B16", "Face amount misparsed with comma as decimal separator",
       "A locale-dependent parser read the thousands comma as a decimal point, so '250,000.00' loaded as 250.00. "
       "The value parses and is positive, but is 1000x too small.")
facec = [k for k in inscope_live if lp_by[k]["FACE_AMT"] in ("250,000.00", "750,000.00")]
for k in take(facec, 2, used_pol):
    tp_by[k]["face_amount"] = lp_by[k]["FACE_AMT"].split(",")[0] + ".00"
    inst("B16", "policies", k, ("pol", k), "face_amount")

defect("B17", "Issue date shifted one day early",
       "A timezone conversion (local midnight to UTC, then truncated) moved issue_date back by one day on a batch of "
       "policies. Every value is a valid ISO date.")
for k in take(inscope_live, 30, used_pol):
    d = dt.date.fromisoformat(tp_by[k]["issue_date"])
    tp_by[k]["issue_date"] = (d - dt.timedelta(days=1)).isoformat()
    inst("B17", "policies", k, ("pol", k), "issue_date")

defect("B18", "Product valid but wrong",
       "Some TL20 policies were loaded as product Term 10: a valid picklist label, wrong for the row.")
tl20 = [k for k in inscope_live if lp_by[k]["PLAN_CD"] == "TL20"]
for k in take(tl20, 5, used_pol):
    tp_by[k]["product"] = "Term 10"
    inst("B18", "policies", k, ("pol", k), "product")

defect("B19", "Policy linked to a same-name account",
       "The parent lookup matched on account name instead of the CUST_NO cross-reference, so some policies hang off a "
       "different customer who happens to share the name. The parent account exists and its name matches, but it "
       "is not the account whose legacy_cust_no equals the policy's CUST_NO.")
byname = defaultdict(list)
for c in sorted(la_by):
    r = la_by[c]
    if pol_count[acc_id_of[c]] > 0 and c not in used_acc:
        byname[r["CUST_NAME"]].append(c)
namegroups = sorted(n for n, cs in byname.items() if len(cs) >= 2)
for nm in rng.sample(namegroups, 4):
    src, dst = rng.sample(byname[nm], 2)
    used_acc.update((src, dst))
    pols = [k for k in inscope_live if lp_by[k]["CUST_NO"] == src and k not in used_pol]
    k = rng.choice(sorted(pols))
    used_pol.add(k)
    tp_by[k]["account_id"] = acc_id_of[dst]
    inst("B19", "policies", k, ("pol", k), "account_id")

defect("B20", "Policy re-keyed (cross-reference truncated)",
       "legacy_pol_no was truncated to 9 characters on two policies (dropped last digit). Each legacy policy therefore "
       "has no target row (instance with target_row null) and each target row has no legacy counterpart (instance "
       "keyed by the truncated cross-reference). Values are otherwise correct, so control totals tie.")
allp = set(lp_by)
for k in take(inscope_live, 2, used_pol):
    bad = k[:9]
    assert bad not in allp
    tp_by[k]["legacy_pol_no"] = bad
    inst("B20", "policies", k, None, None)
    inst("B20", "policies", bad, ("pol", k), None)

defect("B21", "Parent link blank",
       "account_id is blank on two policies (required field). The parent account exists in the target; the link was "
       "not populated.")
for k in take(inscope_live, 2, used_pol):
    tp_by[k]["account_id"] = ""
    inst("B21", "policies", k, ("pol", k), "account_id")

# policy decoys: scope-boundary dates in legacy that the clean target already handles correctly
lp_inscope_lp = [k for k in inscope_live if lp_by[k]["STATUS"] == "LP"]
for k in take(lp_inscope_lp, 1, used_pol):
    lp_by[k]["LAPSE_DT"] = "01/01/2019"
    decoys.append({"entity": "policies", "key": k, "field": None,
                   "note": "LAPSE_DT set to the cutoff 01/01/2019: in scope, correctly migrated"})
for k in take([x for x in oos if lp_by[x]["PLAN_CD"] != "DI"], 1, used_pol):
    lp_by[k]["LAPSE_DT"] = "12/31/2018"
    decoys.append({"entity": "policies", "key": k, "field": None,
                   "note": "LAPSE_DT set to 12/31/2018: out of scope, correctly not migrated"})

# ---------------------------------------------------------------- assemble target accounts
acc_rows = []
for r in ta:
    cust = cust_of_acc[r["account_id"]]
    if cust in b7:
        inst("B7", "accounts", cust, None, None)
        continue
    acc_rows.append(r)
next_acc = len(ta) + 1
for c in b6:
    dup = dict(ta_by[c])
    dup["account_id"] = f"ACC-{next_acc:06d}"
    next_acc += 1
    acc_rows.append(dup)
    inst("B6", "accounts", c, ("accdup", dup["account_id"]), None)
test = {"account_id": f"ACC-{next_acc:06d}", "legacy_cust_no": "", "account_name": "TEST ACCOUNT - DO NOT USE",
        "account_type": "Individual", "state": "MA", "opened_on": "2026-09-28", "status": "Active",
        "created_by": "MIGRATION"}
acc_rows.append(test)
inst("B9", "accounts", None, ("accdup", test["account_id"]), None)

# ---------------------------------------------------------------- assemble target policies
removed = set(b11) | set(b12)
for k in b11:
    inst("B11", "policies", k, None, None)
for k in b12:
    inst("B12", "policies", k, None, None)

next_pol = len(tp) + 1
inserted = {}
for k in di_oos:
    s = lp_by[k]
    inserted[k] = {
        "policy_id": f"POL-{next_pol:07d}", "legacy_pol_no": k, "account_id": acc_id_of[s["CUST_NO"]],
        "product": pmaps["PLAN_CD"][s["PLAN_CD"]], "billing_mode": pmaps["MODE"][s["MODE"]],
        "annual_premium": s["ANN_PREM"].replace(",", ""), "face_amount": s["FACE_AMT"].replace(",", ""),
        "issue_date": ldate(s["ISSUE_DT"]).isoformat(), "status": pmaps["STATUS"][s["STATUS"]],
        "created_by": "MIGRATION"}
    next_pol += 1

# merge clean target rows and inserted DI rows in legacy order
pol_rows = []
stream = sorted([(lp_pos[k], ("orig", k)) for k in order] + [(lp_pos[k], ("ins", k)) for k in di_oos])
for _, (kind, k) in stream:
    if kind == "orig":
        if k in removed:
            continue
        pol_rows.append(tp_by[k])
    else:
        pol_rows.append(inserted[k])
        inst("B10", "policies", k, ("pol", k), None)
for k in b13:
    dup = dict(tp_by[k])
    dup["policy_id"] = f"POL-{next_pol:07d}"
    next_pol += 1
    pol_rows.append(dup)
    inst("B13", "policies", k, ("poldup", dup["policy_id"]), None)

# ---------------------------------------------------------------- write outputs
OUT.mkdir(exist_ok=True)
SEALED.mkdir(exist_ok=True)
write("legacy_accounts.csv", la_h, la)
write("legacy_policies.csv", lp_h, lp)
write("target_accounts.csv", ta_h, acc_rows)
write("target_policies.csv", tp_h, pol_rows)
for f in ("mapping.json", "exceptions.csv", "DATA.md"):
    shutil.copyfile(CLEAN / f, OUT / f)

# resolve target rows (line numbers: header is line 1)
acc_obj = {id(r): cust_of_acc[r["account_id"]] for r in ta}
acc_line = {}
for i, r in enumerate(acc_rows):
    acc_line[("accdup", r["account_id"])] = i + 2
    if id(r) in acc_obj:
        acc_line[("acc", acc_obj[id(r)])] = i + 2
pol_obj = {id(tp_by[k]): k for k in order}
pol_obj.update({id(v): k for k, v in inserted.items()})
pol_line = {}
for i, r in enumerate(pol_rows):
    pol_line[("poldup", r["policy_id"])] = i + 2
    if id(r) in pol_obj:
        pol_line[("pol", pol_obj[id(r)])] = i + 2

instances = []
for p in plan:
    row = None
    if p["row"] is not None:
        row = acc_line[p["row"]] if p["entity"] == "accounts" else pol_line[p["row"]]
    instances.append({"defect": p["defect"], "entity": p["entity"], "key": p["key"],
                      "target_row": row, "field": p["field"]})
order_ids = [d["id"] for d in defects]
instances.sort(key=lambda x: (order_ids.index(x["defect"]), x["entity"], str(x["key"]), x["target_row"] or 0))

key = {"defects": defects, "instances": instances,
       "decoys": decoys,
       "notes": "decoys are planted spec-compliant variations, not defects; a flag on one is a false positive."}
(SEALED / "answer_key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
print(f"defect classes: {len(defects)}  instances: {len(instances)}  decoys: {len(decoys)}")
