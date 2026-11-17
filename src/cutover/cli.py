"""cutover check | generate | score."""

import argparse
import json
import sys
from pathlib import Path

from cutover.migration import load_migration
from cutover.report import to_markdown
from cutover.runner import run_checks
from cutover.spec import DEFAULT_SPEC, load_spec


def _check(args) -> int:
    m = load_migration(args.folder, load_spec(args.spec), args.exceptions)
    report = run_checks(m)
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_dict(), indent=1), encoding="utf-8")
    sys.stdout.write(to_markdown(report))
    return 0 if report.readiness["status"] == "READY" else 1


def _generate(args) -> int:
    from cutover.synth.scenario import write_scenario

    defects = (
        {"all": None, "none": []}.get(args.defects)
        if args.defects in ("all", "none")
        else (args.defects.split(","))
    )
    write_scenario(args.out, seed=args.seed, scale=args.scale, defects=defects)
    print(f"wrote {args.out}")
    return 0


def _score(args) -> int:
    from cutover.score import score

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    key = json.loads(Path(args.answer_key).read_text(encoding="utf-8"))
    print(json.dumps(score(report, key), indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cutover")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="tie out a migration folder")
    c.add_argument("folder")
    c.add_argument("--spec", default=str(DEFAULT_SPEC))
    c.add_argument("--exceptions", help="exception register (default: folder/exceptions.csv)")
    c.add_argument("--json", help="also write the full report as JSON")
    c.set_defaults(fn=_check)

    g = sub.add_parser("generate", help="write a synthetic migration")
    g.add_argument("out")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--scale", choices=["gate", "demo"], default="gate")
    g.add_argument("--defects", default="all", help="all | none | D1,D3,...")
    g.set_defaults(fn=_generate)

    s = sub.add_parser("score", help="score a JSON report against an answer key")
    s.add_argument("report")
    s.add_argument("answer_key")
    s.set_defaults(fn=_score)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
