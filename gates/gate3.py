"""Gate 3: one run of the frozen checker on the blind defect set, scored as registered.

    py gates/gate3.py <blind folder>

The blind folder holds the subagent's inject.py, defected/ and sealed/answer_key.json.
It is copied into gates/blind/ for the record, then checked once. Bars (SCOPE.md):
class recall >= 80%, instance recall >= 90%, zero blocker findings on rows outside
the answer key. Detection uses the Gate 2 rule (score._names): same entity, same
key or target row, and the same field for a field-level instance.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cutover.migration import load_migration  # noqa: E402
from cutover.models import BLOCKER  # noqa: E402
from cutover.runner import run_checks  # noqa: E402
from cutover.score import AGGREGATE, _names  # noqa: E402
from cutover.spec import DEFAULT_SPEC, load_spec  # noqa: E402

FROZEN = "39cb853"


def _same_row(f: dict, inst: dict) -> bool:
    return _names(f, {**inst, "field": None})


def main(blind: Path) -> int:
    changed = subprocess.run(
        ["git", "diff", "--stat", FROZEN, "--", "src", "spec"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if changed:
        print(f"checker changed since {FROZEN}; Gate 3 must run on the frozen checker:\n{changed}")
        return 2

    record = ROOT / "gates" / "blind"
    if record.exists():
        shutil.rmtree(record)
    shutil.copytree(blind / "defected", record / "defected")
    shutil.copytree(blind / "sealed", record / "sealed")
    shutil.copy(blind / "inject.py", record / "inject.py")
    spec_same = (record / "defected" / "mapping.json").read_bytes() == DEFAULT_SPEC.read_bytes()

    report = run_checks(load_migration(record / "defected", load_spec(DEFAULT_SPEC))).to_dict()
    key = json.loads((record / "sealed" / "answer_key.json").read_text(encoding="utf-8"))
    instances = key["instances"]

    findings = [f for c in report["checks"] for f in c["findings"] if not f["waived"]]
    rows = [f for f in findings if f["kind"] not in AGGREGATE]
    detected = [any(_names(f, i) for f in rows) for i in instances]
    by_class: dict[str, list[int]] = {}
    for inst, hit in zip(instances, detected, strict=True):
        n = by_class.setdefault(inst["defect"], [0, 0, set()])
        n[0] += 1
        n[1] += hit
        n[2] |= {f["check"] for f in rows if _names(f, inst)}
    outside = [f for f in rows if not any(_same_row(f, i) for i in instances)]
    false_blockers = [f for f in outside if f["severity"] == BLOCKER]

    titles = {d["id"]: d["title"] for d in key["defects"]}
    classes = sorted(by_class, key=lambda d: int("".join(c for c in d if c.isdigit()) or 0))
    class_recall = sum(by_class[d][1] > 0 for d in classes) / len(classes)
    instance_recall = sum(detected) / len(instances)
    passed = class_recall >= 0.8 and instance_recall >= 0.9 and not false_blockers

    result = {
        "gate": 3,
        "frozen_checker": FROZEN,
        "spec_unchanged": spec_same,
        "pass": passed,
        "class_recall": class_recall,
        "classes": len(classes),
        "classes_detected": sum(by_class[d][1] > 0 for d in classes),
        "instance_recall": instance_recall,
        "instances": len(instances),
        "instances_detected": sum(detected),
        "false_blockers": len(false_blockers),
        "outside_key_warnings": len(outside) - len(false_blockers),
        "aggregate_findings": len(findings) - len(rows),
        "readiness": report["readiness"]["status"],
        "by_class": {
            d: {
                "title": titles.get(d),
                "instances": by_class[d][0],
                "detected": by_class[d][1],
                "caught_by": sorted(by_class[d][2]),
            }
            for d in classes
        },
        "missed": [i for i, hit in zip(instances, detected, strict=True) if not hit],
        "outside_key": outside,
    }
    out = ROOT / "gates" / "results"
    (out / "gate3_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "gate3.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"Gate 3: {'PASS' if passed else 'FAIL'}")
    print(
        f"  class recall {result['classes_detected']}/{len(classes)} = {class_recall:.0%} (bar 80%)"
    )
    print(f"  instance recall {sum(detected)}/{len(instances)} = {instance_recall:.1%} (bar 90%)")
    print(f"  blocker findings outside the key: {len(false_blockers)} (bar 0)")
    for d in classes:
        n = by_class[d]
        print(f"  {d} {titles.get(d)}: {n[1]}/{n[0]} via {sorted(n[2])}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
