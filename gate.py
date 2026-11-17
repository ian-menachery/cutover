#!/usr/bin/env python3
"""Gate 0, the definition of done for the code. Stdlib only, no make.

Lint, format, tests with the coverage floor (pyproject's fail_under), and a
clean tree. HEAD must be pushed when a remote exists; until the repo has one,
that part is skipped and said so.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def _run(cmd: list[str]) -> tuple[bool, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def clean_tree() -> tuple[bool, str]:
    ok, out = _run(["git", "status", "--porcelain"])
    if not ok or out:
        return False, "working tree is dirty:\n" + out
    ok, remotes = _run(["git", "remote"])
    if not remotes:
        return True, "no remote yet: pushed-HEAD check skipped"
    ok, out = _run(["git", "fetch", "origin"])
    if not ok:
        return False, out
    ok, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    ok, ahead = _run(["git", "log", f"origin/{branch}..HEAD", "--oneline"])
    if not ok or ahead:
        return False, f"HEAD is not pushed to origin/{branch}:\n{ahead}"
    return True, ""


TARGETS = (
    ("ruff check", lambda: _run([PY, "-m", "ruff", "check", "src", "tests", "gates", "gate.py"])),
    (
        "ruff format --check",
        lambda: _run([PY, "-m", "ruff", "format", "--check", "src", "tests", "gates", "gate.py"]),
    ),
    (
        "pytest --cov=cutover.checks (floor 85%)",
        lambda: _run([PY, "-m", "pytest", "--cov=cutover.checks"]),
    ),
    ("clean tree", clean_tree),
)


def main() -> int:
    for name, target in TARGETS:
        ok, detail = target()
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if detail and (not ok or name == "clean tree"):
            print("\n".join(f"      {line}" for line in detail.splitlines()[-30:]))
        if not ok:
            print(f"\nGATE FAIL at: {name}")
            return 1
    print("\nGATE PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
