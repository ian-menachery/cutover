import pytest

from cutover.migration import load_migration
from cutover.runner import run_checks
from cutover.score import score
from cutover.synth.scenario import answer_key, build, compose, write_tables

ALL = {f"D{i}" for i in range(1, 10)}


def _run(tmp_path, built, enabled):
    tables = compose(built, enabled)
    write_tables(tmp_path, built.spec, tables, built.register)
    report = run_checks(load_migration(tmp_path, built.spec)).to_dict()
    return report, answer_key(built, tables, enabled)


def test_build_is_deterministic():
    a, b = build(7, "demo"), build(7, "demo")
    assert a.tables == b.tables
    assert [d.ops for d in a.defects] == [d.ops for d in b.defects]


def test_row_level_defects_use_disjoint_rows():
    built = build(3, "demo")
    keys = {}
    for d in built.defects:
        for i in d.instances:
            if i["field"] is None:
                assert (i["entity"], i["key"]) not in keys, (
                    d.id,
                    keys.get((i["entity"], i["key"])),
                )
                keys[(i["entity"], i["key"])] = d.id


def test_clean_demo_is_ready(tmp_path):
    report, _ = _run(tmp_path, build(1, "demo"), set())
    assert report["readiness"]["status"] == "READY"
    assert report["readiness"]["known_exceptions"] == 4


@pytest.mark.parametrize("defect", sorted(ALL, key=lambda d: int(d[1:])))
def test_each_defect_alone_is_found_with_no_false_positives(tmp_path, defect):
    report, key = _run(tmp_path, build(2, "demo"), {defect})
    s = score(report, key)
    assert s["instance_recall"] == 1.0
    assert s["false_positives"] == 0


def test_all_defects_demo(tmp_path):
    report, key = _run(tmp_path, build(1, "demo"), ALL)
    s = score(report, key)
    assert (s["instance_recall"], s["false_positives"], s["classes_detected"]) == (1.0, 0, 9)
    assert report["readiness"]["status"] == "BLOCKED"
    assert any(w["field"] == "account_name" for w in report["readiness"]["warnings"])
    assert not any(b["field"] == "account_name" for b in report["readiness"]["blockers"])


def test_score_flags_a_false_positive():
    report = {
        "checks": [
            {
                "findings": [
                    {
                        "check": "R3",
                        "entity": "policies",
                        "kind": "missing_in_target",
                        "key": "P1",
                        "target_row": None,
                        "field": None,
                        "waived": False,
                    },
                    {
                        "check": "R5",
                        "entity": "policies",
                        "kind": "control_total_mismatch",
                        "key": None,
                        "target_row": None,
                        "field": "count",
                        "group": {"product": "X"},
                        "waived": False,
                    },
                ]
            }
        ]
    }
    key = {
        "instances": [
            {
                "defect": "D1",
                "entity": "policies",
                "key": "P2",
                "target_row": None,
                "field": None,
                "groups": [["Y"]],
            }
        ]
    }
    s = score(report, key)
    assert (s["detected"], s["false_positives"]) == (0, 2)
