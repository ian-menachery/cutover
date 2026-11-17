"""Score a report against an answer key: recall, precision, and which checks caught what.

Rules, fixed in SCOPE.md before the checks were written:

- An instance is detected when an unwaived finding names its row (same entity,
  and the same key or the same target row) and, for a field-level instance,
  its field. Count and control-total findings cannot name a row, so they never
  count toward recall.
- A row finding is a true positive when it matches an instance by that rule. A
  control-total finding is a true positive when its group is one an instance
  touches; a count finding when its entity has an instance.
"""

from collections import defaultdict

AGGREGATE = {"count_mismatch", "control_total_mismatch"}


def _names(f: dict, inst: dict) -> bool:
    if f["entity"] != inst["entity"]:
        return False
    same_key = f["key"] is not None and f["key"] == inst["key"]
    same_row = f["target_row"] is not None and f["target_row"] == inst["target_row"]
    if not (same_key or same_row):
        return False
    return inst["field"] is None or f["field"] == inst["field"]


def score(report: dict, key: dict) -> dict:
    instances = key["instances"]
    findings = [f for c in report["checks"] for f in c["findings"] if not f["waived"]]
    rows = [f for f in findings if f["kind"] not in AGGREGATE]

    by_entity: dict[str, list] = defaultdict(list)
    for f in rows:
        by_entity[f["entity"]].append(f)

    caught_by: dict[str, set] = defaultdict(set)
    detected: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    for inst in instances:
        total[inst["defect"]] += 1
        hits = [f for f in by_entity[inst["entity"]] if _names(f, inst)]
        if hits:
            detected[inst["defect"]] += 1
            caught_by[inst["defect"]] |= {f["check"] for f in hits}

    groups = defaultdict(set)
    for inst in instances:
        for g in inst["groups"]:
            groups[(inst["entity"], tuple(g))].add(inst["defect"])
    entities = {i["entity"] for i in instances}

    false_positives = []
    for f in findings:
        if f["kind"] == "count_mismatch":
            ok = f["entity"] in entities
            for i in instances:  # credit only the instances that move a count
                if i["entity"] == f["entity"] and i.get("moves_count"):
                    caught_by[i["defect"]].add(f["check"])
        elif f["kind"] == "control_total_mismatch":
            hit = groups.get((f["entity"], tuple(f["group"].values())), set())
            ok = bool(hit)
            for d in hit:
                caught_by[d].add(f["check"])
        else:
            ok = any(_names(f, i) for i in instances if i["entity"] == f["entity"])
        if not ok:
            false_positives.append(f)

    n_inst = len(instances)
    classes = sorted(total, key=lambda d: int(d[1:]))
    return {
        "instances": n_inst,
        "detected": sum(detected.values()),
        "instance_recall": (sum(detected.values()) / n_inst) if n_inst else None,
        "classes": len(classes),
        "classes_detected": sum(detected[d] > 0 for d in classes),
        "findings": len(findings),
        "false_positives": len(false_positives),
        "precision": (1 - len(false_positives) / len(findings)) if findings else None,
        "by_defect": {
            d: {
                "instances": total[d],
                "detected": detected[d],
                "caught_by": sorted(caught_by[d], key=lambda c: int(c[1:])),
            }
            for d in classes
        },
        "false_positive_findings": false_positives[:50],
    }
