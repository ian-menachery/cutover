import csv

from conftest import SPEC, findings

from cutover.migration import load_migration
from cutover.report import to_markdown
from cutover.runner import run_checks


def test_stale_exception_is_reported(mini):
    register = [
        {
            "check": "R3",
            "entity": "policies",
            "key": "P000000001",
            "reason": "pending",
            "ticket": "MIG-1",
        }
    ]
    report = mini(register=register)  # P1 migrated after all
    assert report.readiness["stale_exceptions"] == [
        {"check": "R3", "entity": "policies", "key": "P000000001", "ticket": "MIG-1"}
    ]
    assert findings(report, "R1")[0].expected == "2"  # the register still defers it


def test_missing_file_skips_and_blocks(mini, tmp_path):
    mini()
    (tmp_path / "target_policies.csv").unlink()
    report = run_checks(load_migration(tmp_path, SPEC))
    statuses = {c.id: c.status for c in report.checks}
    assert statuses["R1"] == "skip" and statuses["R8"] == "skip"
    assert "target_policies.csv not found" in report.checks[0].message
    assert report.readiness["status"] == "BLOCKED"
    assert report.readiness["skipped"] == [c.id for c in report.checks]


def test_missing_column_skips(mini, tmp_path):
    mini()
    path = tmp_path / "target_accounts.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    with path.open("w", newline="", encoding="utf-8") as fh:
        cols = [c for c in rows[0] if c != "state"]
        w = csv.DictWriter(fh, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    report = run_checks(load_migration(tmp_path, SPEC))
    assert "lacks column(s) state" in report.checks[0].message


def test_row_numbers_survive_quoted_commas(mini, tmp_path):
    report = mini(lambda legacy, target: target["accounts"][2].update(account_name='A, "B" C'))
    (f,) = findings(report, "R6")
    assert (f.source_row, f.target_row, f.found) == (4, 4, 'A, "B" C')


def test_markdown_leads_with_readiness(mini):
    report = mini(lambda legacy, target: target["policies"].pop())
    text = to_markdown(report)
    assert text.splitlines()[2] == "**Go-live readiness: BLOCKED**"
    assert "R3 policies  missing_in_target: 1" in text
