"""Gates 1 and 2: seeds 1-20 at gate scale, bars as registered in SCOPE.md.

    py gates/run_gates.py          # both
    py gates/run_gates.py 1        # one

Writes gates/results/gate<N>.json and prints the verdict. Scenario files go to
gates/work/ (git-ignored); every result is reproducible from the seed.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cutover.migration import load_migration  # noqa: E402
from cutover.runner import run_checks  # noqa: E402
from cutover.score import score  # noqa: E402
from cutover.synth.scenario import answer_key, build, compose, write_tables  # noqa: E402

SEEDS = range(1, 21)
ALL = {f"D{i}" for i in range(1, 10)}
PREDICTED = {
    "D1": ["R1", "R3", "R5"],
    "D2": ["R1", "R2"],
    "D3": ["R5", "R6"],
    "D4": ["R5", "R7"],
    "D5": ["R6"],
    "D6": ["R6"],
    "D7": ["R2", "R3"],
    "D8": ["R1", "R4", "R5"],
    "D9": ["R6", "R8"],
}
WORK, RESULTS = ROOT / "gates" / "work", ROOT / "gates" / "results"


def _run(seed: int, enabled: set[str]) -> tuple[dict, dict]:
    built = build(seed, "gate")
    tables = compose(built, enabled)
    folder = WORK / f"{'all' if enabled else 'clean'}-{seed:02d}"
    write_tables(folder, built.spec, tables, built.register)
    report = run_checks(load_migration(folder, built.spec)).to_dict()
    return report, answer_key(built, tables, enabled)


def gate1() -> dict:
    rows = []
    for seed in SEEDS:
        report, _ = _run(seed, set())
        r = report["readiness"]
        open_ = [f for c in report["checks"] for f in c["findings"] if not f["waived"]]
        rows.append(
            {
                "seed": seed,
                "open_findings": len(open_),
                "known_exceptions": r["known_exceptions"],
                "stale": len(r["stale_exceptions"]),
                "skipped": len(r["skipped"]),
                "readiness": r["status"],
                "first_open": open_[:5],
            }
        )
    passed = all(
        x["open_findings"] == 0
        and x["known_exceptions"] == 4
        and x["stale"] == 0
        and x["skipped"] == 0
        and x["readiness"] == "READY"
        for x in rows
    )
    return {"gate": 1, "pass": passed, "seeds": rows}


def gate2() -> dict:
    rows, caught = [], {d: set() for d in PREDICTED}
    for seed in SEEDS:
        report, key = _run(seed, ALL)
        s = score(report, key)
        r = report["readiness"]
        for d, v in s["by_defect"].items():
            caught[d] |= set(v["caught_by"])
        rows.append(
            {
                "seed": seed,
                "instances": s["instances"],
                "detected": s["detected"],
                "classes_detected": s["classes_detected"],
                "findings": s["findings"],
                "false_positives": s["false_positives"],
                "readiness": r["status"],
                "d6_warning_only": any(w["field"] == "account_name" for w in r["warnings"])
                and not any(b["field"] == "account_name" for b in r["blockers"]),
                "by_defect": {
                    d: [v["instances"], v["detected"]] for d, v in s["by_defect"].items()
                },
                "first_false_positives": s["false_positive_findings"][:5],
            }
        )
    instances = sum(x["instances"] for x in rows)
    detected = sum(x["detected"] for x in rows)
    findings = sum(x["findings"] for x in rows)
    fps = sum(x["false_positives"] for x in rows)
    passed = (
        all(x["classes_detected"] == 9 for x in rows)
        and detected == instances
        and fps == 0
        and all(x["readiness"] == "BLOCKED" and x["d6_warning_only"] for x in rows)
    )
    return {
        "gate": 2,
        "pass": passed,
        "pooled": {
            "instances": instances,
            "detected": detected,
            "instance_recall": detected / instances,
            "findings": findings,
            "false_positives": fps,
            "precision": 1 - fps / findings,
        },
        "caught_by": {
            d: {"predicted": PREDICTED[d], "actual": sorted(caught[d], key=lambda c: int(c[1:]))}
            for d in PREDICTED
        },
        "seeds": rows,
    }


def main(argv: list[str]) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    wanted = argv or ["1", "2"]
    ok = True
    for g in wanted:
        t0 = time.perf_counter()
        result = {"1": gate1, "2": gate2}[g]()
        result["seconds"] = round(time.perf_counter() - t0, 1)
        (RESULTS / f"gate{g}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"Gate {g}: {'PASS' if result['pass'] else 'FAIL'} ({result['seconds']} s)")
        if g == "2":
            print(json.dumps(result["pooled"]))
            for d, v in result["caught_by"].items():
                flag = "" if v["predicted"] == v["actual"] else "  <- differs from prediction"
                print(f"  {d}: predicted {v['predicted']} actual {v['actual']}{flag}")
        ok &= result["pass"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
