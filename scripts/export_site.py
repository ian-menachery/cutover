"""Export the demo data and the Python reference reports for the site's TypeScript port.

    py scripts/export_site.py

Writes handoff/site/data/cutover/demo.json (clean demo migration, register,
spec, the nine defects as patches) and reference.json (this engine's report
for 21 defect combinations: clean, each alone, all nine, 10 seeded random).
"""

import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cutover.migration import load_migration  # noqa: E402
from cutover.runner import run_checks  # noqa: E402
from cutover.spec import DEFAULT_SPEC  # noqa: E402
from cutover.synth.scenario import (  # noqa: E402
    SOURCE_COLUMNS,
    TARGET_COLUMNS,
    build,
    compose,
    write_tables,
)

OUT = ROOT / "handoff" / "site" / "data" / "cutover"
SEED, SCALE = 1, "demo"
IDS = [f"D{i}" for i in range(1, 10)]


def cases() -> list[tuple[str, list[str]]]:
    rng = random.Random(2026)
    out = [("clean", [])] + [(d, [d]) for d in IDS] + [("all", IDS)]
    seen = {tuple(c) for _, c in out}
    while len(out) < 21:
        pick = sorted(rng.sample(IDS, rng.randint(2, 7)), key=lambda d: int(d[1:]))
        if tuple(pick) not in seen:
            seen.add(tuple(pick))
            out.append(("+".join(pick), pick))
    return out


def main() -> int:
    built = build(SEED, SCALE)
    OUT.mkdir(parents=True, exist_ok=True)
    columns = {"source": SOURCE_COLUMNS, "target": TARGET_COLUMNS}
    demo = {
        "seed": SEED,
        "scale": SCALE,
        "spec": json.loads(DEFAULT_SPEC.read_text(encoding="utf-8")),
        "register": built.register,
        "columns": columns,
        "base": {
            side: {
                e: [[r[c] for c in columns[side][e]] for r in rows]
                for e, rows in built.tables[side].items()
            }
            for side in ("source", "target")
        },
        "defects": [
            {"id": d.id, "title": d.title, "description": d.description, "ops": d.ops}
            for d in built.defects
        ],
    }
    (OUT / "demo.json").write_text(json.dumps(demo, separators=(",", ":")), encoding="utf-8")

    reference = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, enabled in cases():
            folder = Path(tmp) / name
            write_tables(folder, built.spec, compose(built, set(enabled)), built.register)
            report = run_checks(load_migration(folder, built.spec)).to_dict()
            reference.append({"name": name, "defects": enabled, "report": report})
    (OUT / "reference.json").write_text(
        json.dumps({"seed": SEED, "scale": SCALE, "cases": reference}, separators=(",", ":")),
        encoding="utf-8",
    )
    for f in ("demo.json", "reference.json"):
        print(f, round((OUT / f).stat().st_size / 1024), "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
