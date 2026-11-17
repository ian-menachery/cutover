"""Render a report as markdown: readiness first, then the exception report."""

from cutover.models import Report

MAX_ROWS = 25  # display cap per check; the JSON report keeps every finding


def _ref(f) -> str:
    parts = []
    if f.source_row is not None:
        parts.append(f"legacy row {f.source_row}")
    if f.target_row is not None:
        parts.append(f"target row {f.target_row}")
    return ", ".join(parts) or "-"


def to_markdown(report: Report) -> str:
    r = report.readiness
    lines = [f"# Cutover tie-out: {report.spec}", "", f"**Go-live readiness: {r['status']}**", ""]
    if r["blockers"]:
        lines += ["Blocks sign-off:", ""]
        lines += [
            f"- {b['check']} {b['entity']} {b['field'] or ''} {b['kind']}: {b['count']}"
            for b in r["blockers"]
        ]
        lines.append("")
    if r["warnings"]:
        lines += ["Warnings to acknowledge:", ""]
        lines += [
            f"- {w['check']} {w['entity']} {w['field'] or ''} {w['kind']}: {w['count']}"
            for w in r["warnings"]
        ]
        lines.append("")
    if r["skipped"]:
        lines += [f"Not verified (skipped): {', '.join(r['skipped'])}", ""]
    lines.append(f"Known exceptions: {r['known_exceptions']}")
    for s in r["stale_exceptions"]:
        lines.append(f"- stale exception: {s['check']} {s['entity']} {s['key']} ({s['ticket']})")
    lines += ["", "| Check | Status | Result |", "|---|---|---|"]
    lines += [f"| {c.id} {c.name} | {c.status.upper()} | {c.message} |" for c in report.checks]

    for c in report.checks:
        if not c.findings:
            continue
        lines += [
            "",
            f"## {c.id} {c.name}",
            "",
            "| Severity | Ref | Finding |",
            "|---|---|---|",
        ]
        for f in c.findings[:MAX_ROWS]:
            sev = "known exception" if f.waived else f.severity
            note = f" ({f.ticket})" if f.ticket else ""
            lines.append(f"| {sev} | {_ref(f)} | {f.message}{note} |")
        if len(c.findings) > MAX_ROWS:
            lines.append(f"| | | ...and {len(c.findings) - MAX_ROWS} more in the JSON report |")
    return "\n".join(lines) + "\n"
