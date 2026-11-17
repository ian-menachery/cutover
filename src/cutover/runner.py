"""Run every check, apply the exception register, and decide go-live readiness.

A finding that matches a register entry on (check, entity, key) is a known
exception: it stays in the report, marked waived with its ticket, and does not
block sign-off. A register entry that matches nothing is stale. Readiness is
BLOCKED when any unwaived blocker exists or any check skipped, since a skipped
check means part of the migration was never verified.
"""

from cutover.checks import CHECKS
from cutover.migration import Migration
from cutover.models import BLOCKER, FAIL, PASS, SKIP, CheckResult, Finding, Report

FILES = {"src": "source_file", "tgt": "target_file"}


def _status_message(findings: list[Finding]) -> tuple[str, str]:
    open_ = sum(not f.waived for f in findings)
    waived = len(findings) - open_
    known = f"{waived} known exception(s)"
    if open_:
        return FAIL, f"{open_} finding(s)" + (f", {known}" if waived else "") + "."
    return PASS, (f"No open findings; {known}." if waived else "No findings.")


def _summary(results: list[CheckResult], severity: str) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for r in results:
        for f in r.findings:
            if f.waived or f.severity != severity:
                continue
            k = (r.id, f.entity, f.kind, f.field)
            if k not in groups:
                groups[k] = {
                    "check": r.id,
                    "name": r.name,
                    "entity": f.entity,
                    "kind": f.kind,
                    "field": f.field,
                    "count": 0,
                }
            groups[k]["count"] += 1
    return list(groups.values())


def run_checks(m: Migration) -> Report:
    register = {(e.check, e.entity, e.key): e for e in m.register}
    used: set[tuple] = set()
    results: list[CheckResult] = []

    for check in CHECKS:
        missing = [t for t in check.requires(m.spec) if t not in m.present]
        if missing:
            why = "; ".join(m.problems.get(t, f"{t} not loaded") for t in missing)
            results.append(CheckResult(check.id, check.name, SKIP, f"Not run: {why}."))
            continue
        findings = check.run(m)
        for f in findings:
            entry = register.get((f.check, f.entity, f.key)) if f.key else None
            if entry:
                f.waived, f.ticket = True, entry.ticket
                used.add((entry.check, entry.entity, entry.key))
        status, message = _status_message(findings)
        results.append(CheckResult(check.id, check.name, status, message, findings))

    stale = [
        {"check": e.check, "entity": e.entity, "key": e.key, "ticket": e.ticket}
        for e in m.register
        if (e.check, e.entity, e.key) not in used
    ]
    blockers = _summary(results, BLOCKER)
    skipped = [r.id for r in results if r.status == SKIP]
    readiness = {
        "status": "BLOCKED" if blockers or skipped else "READY",
        "blockers": blockers,
        "warnings": _summary(results, "warning"),
        "known_exceptions": sum(f.waived for r in results for f in r.findings),
        "stale_exceptions": stale,
        "skipped": skipped,
    }
    return Report(spec=m.spec.name, checks=results, readiness=readiness)
