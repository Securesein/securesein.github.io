#!/usr/bin/env python3
"""
The pipeline's test runner. Deliberately dependency-free — no pytest,
no fixtures framework — because scripts/requirements.txt is installed
into a CI job whose whole purpose is to publish, and a test harness is
not something that job should be carrying.

    python3 scripts/tests/run_tests.py [pattern ...]

Collects every `test_*` function from every `test_*.py` beside it, runs
them, and reports. A test is a function that raises on failure; that is
the entire contract.

NOTHING HERE TOUCHES THE NETWORK OR A PAID API. Tests that need model
output use the deterministic offline path (core/llm.py), and tests that
need feed data use the recorded fixtures in scripts/tests/fixtures/.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

# Every state write during a test run goes to a throwaway directory.
# Set BEFORE core.constants is imported by anything, so the real
# state/ never picks up a test's rejections or adapter failures.
os.environ.setdefault(
    "SECURESEIN_STATE_DIR", tempfile.mkdtemp(prefix="securesein-test-state-")
)
# Same for the Radar: a test must not put rows in the committed
# src/content/radar/ collection, where they would reach the Astro build.
os.environ.setdefault(
    "SECURESEIN_RADAR_DIR", tempfile.mkdtemp(prefix="securesein-test-radar-")
)


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(patterns: list[str]) -> int:
    passed, failed = 0, []
    for path in sorted(HERE.glob("test_*.py")):
        module = load(path)
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            if patterns and not any(p in f"{path.stem}.{name}" for p in patterns):
                continue
            fn = getattr(module, name)
            if not callable(fn):
                continue
            try:
                fn()
            except Exception:  # noqa: BLE001
                failed.append((path.stem, name, traceback.format_exc()))
                print(f"FAIL  {path.stem}.{name}")
            else:
                passed += 1
                print(f"ok    {path.stem}.{name}")

    print(f"\n{passed} passed, {len(failed)} failed")
    for module_name, test_name, trace in failed:
        print(f"\n=== {module_name}.{test_name} ===\n{trace}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
