from conftest import by, findings

from cutover.models import BLOCKER, WARNING


def test_clean_mini_migration_is_ready(mini):
    report = mini()
    assert report.readiness["status"] == "READY"
    assert all(c.status == "pass" and not c.findings for c in report.checks)


def test_scope_rule_keeps_post_2019_lapse_and_excludes_pre_2019(mini):
    def load_p4(legacy, target):  # the ETL wrongly migrates the excluded policy
        p = dict(by(target["policies"], "legacy_pol_no", "P000000001"))
        target["policies"].append({**p, "policy_id": "POL-0000099", "legacy_pol_no": "P000000004"})

    report = mini(load_p4)
    (f,) = findings(report, "R4")
    assert (f.kind, f.key, f.target_row) == ("out_of_scope", "P000000004", 5)
    assert findings(report, "R1")[0].expected == "3"


def test_unparseable_lapse_date_stays_in_scope(mini):
    def garble(legacy, target):
        by(legacy["policies"], "POL_NO", "P000000004")["LAPSE_DT"] = "15/08/2017"

    (f,) = findings(mini(garble), "R3")
    assert (f.key, f.source_row) == ("P000000004", 5)


def test_r1_counts_and_r3_names_the_dropped_row(mini):
    def drop(legacy, target):
        target["policies"].remove(by(target["policies"], "legacy_pol_no", "P000000002"))

    report = mini(drop)
    (count,) = findings(report, "R1")
    assert (count.entity, count.expected, count.found) == ("policies", "3", "2")
    (orphan,) = findings(report, "R3")
    assert (orphan.kind, orphan.key, orphan.source_row) == ("missing_in_target", "P000000002", 3)


def test_r2_blank_and_duplicate_keys(mini):
    def damage(legacy, target):
        by(target["policies"], "legacy_pol_no", "P000000003")["legacy_pol_no"] = " "
        target["accounts"].append({**target["accounts"][0], "account_id": "ACC-000009"})
        legacy["accounts"].append(dict(legacy["accounts"][2]))

    fs = findings(mini(damage), "R2")
    kinds = [(f.kind, f.severity, f.key, f.source_row, f.target_row) for f in fs]
    assert ("duplicate_key", WARNING, "00000003", 4, None) in kinds
    assert ("duplicate_key", WARNING, "00000003", 5, None) in kinds
    assert ("duplicate_key", BLOCKER, "00000001", None, 2) in kinds
    assert ("duplicate_key", BLOCKER, "00000001", None, 5) in kinds
    assert ("blank_key", BLOCKER, None, None, 4) in kinds


def test_r2_duplicates_are_kept_out_of_r3_r4_and_r6(mini):
    def dup(legacy, target):
        copy_ = {**target["accounts"][0], "account_id": "ACC-000009", "account_name": "X"}
        target["accounts"].append(copy_)

    report = mini(dup)
    assert not findings(report, "R3") and not findings(report, "R4")
    assert not findings(report, "R6")


def test_r4_target_row_with_unknown_key(mini):
    def extra(legacy, target):
        p = dict(target["policies"][0])
        target["policies"].append({**p, "policy_id": "POL-0000099", "legacy_pol_no": "P999000001"})

    (f,) = findings(mini(extra), "R4")
    assert (f.kind, f.key, f.target_row) == ("not_in_source", "P999000001", 5)


def test_r5_doubled_premium_breaks_its_group_only(mini):
    def double(legacy, target):
        by(target["policies"], "legacy_pol_no", "P000000002")["annual_premium"] = "6000.00"

    (f,) = findings(mini(double), "R5")
    assert f.group == {"product": "Whole Life", "billing_mode": "Semi-annual"}
    assert (f.field, f.expected, f.found) == ("annual_premium", "3000.00", "6000.00")
    assert "difference 3000.00" in f.message


def test_r5_registered_deferral_is_a_reconciling_item(mini):
    register = [
        {
            "check": "R3",
            "entity": "policies",
            "key": "P000000001",
            "reason": "pending",
            "ticket": "MIG-1",
        }
    ]

    def defer(legacy, target):
        target["policies"].remove(by(target["policies"], "legacy_pol_no", "P000000001"))

    report = mini(defer, register)
    assert report.readiness["status"] == "READY"
    assert report.readiness["known_exceptions"] == 1
    (f,) = findings(report, "R3")
    assert f.waived and f.ticket == "MIG-1"


def test_r6_each_transform(mini):
    def damage(legacy, target):
        a1 = by(target["accounts"], "legacy_cust_no", "00000001")
        a1["account_name"] = "SMITH, JOHN"  # text
        p1 = by(target["policies"], "legacy_pol_no", "P000000001")
        p1["issue_date"] = "2005-10-02"  # date, DD/MM swap
        p1["face_amount"] = "500000"  # same money, different format: no finding
        p2 = by(target["policies"], "legacy_pol_no", "P000000002")
        p2["billing_mode"] = "Annual"  # picklist
        p2["account_id"] = "ACC-000002"  # parent: wrong account
        p3 = by(target["policies"], "legacy_pol_no", "P000000003")
        p3["account_id"] = "ACC-999999"  # parent: no such account
        p3["annual_premium"] = "2,100.00x"  # unparseable target money

    fs = {(f.key, f.field): f for f in findings(mini(damage), "R6")}
    assert set(fs) == {
        ("00000001", "account_name"),
        ("P000000001", "issue_date"),
        ("P000000002", "billing_mode"),
        ("P000000002", "account_id"),
        ("P000000003", "account_id"),
        ("P000000003", "annual_premium"),
    }
    assert fs[("00000001", "account_name")].severity == WARNING
    assert fs[("P000000001", "issue_date")].expected == "2005-02-10"
    assert fs[("P000000002", "account_id")].found == "00000002"
    assert "matches no accounts row" in fs[("P000000003", "account_id")].message
    assert "could not be parsed" in fs[("P000000003", "annual_premium")].message
    assert fs[("P000000002", "billing_mode")].severity == BLOCKER


def test_r6_unparseable_legacy_value_is_a_difference(mini):
    def garble(legacy, target):
        by(legacy["accounts"], "CUST_NO", "00000002")["OPEN_DT"] = "1999-06-30"

    (f,) = findings(mini(garble), "R6")
    assert (f.field, f.source_value, f.expected) == ("opened_on", "1999-06-30", None)


def test_r7_unmapped_code_invalid_label_and_blank_required(mini):
    def damage(legacy, target):
        by(legacy["policies"], "POL_NO", "P000000001")["PLAN_CD"] = "TL15"
        by(target["policies"], "legacy_pol_no", "P000000001")["product"] = ""
        by(target["policies"], "legacy_pol_no", "P000000002")["status"] = "Paid up"

    report = mini(damage)
    fs = [(f.kind, f.key, f.field) for f in findings(report, "R7")]
    assert fs == [
        ("unmapped_source_value", "P000000001", "product"),
        ("blank_required_value", "P000000001", "product"),
        ("invalid_target_value", "P000000002", "status"),
    ]
    # R6 leaves the unmapped field to R7, but still compares the rest of the row.
    assert [(f.key, f.field) for f in findings(report, "R6")] == [("P000000002", "status")]
    groups = [f.group["product"] for f in findings(report, "R5")]
    assert None in groups and "UNMAPPED(TL15)" in groups


def test_r8_dangling_and_blank_parent(mini):
    def damage(legacy, target):
        by(target["policies"], "legacy_pol_no", "P000000001")["account_id"] = ""
        by(target["policies"], "legacy_pol_no", "P000000003")["account_id"] = "ACC-999999"

    fs = [(f.key, f.target_row, f.found) for f in findings(mini(damage), "R8")]
    assert fs == [("P000000001", 2, None), ("P000000003", 4, "ACC-999999")]
