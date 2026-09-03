"""
Dev helper: un-marks one arbitrary item ID in data/gezien.json so the
next pipeline run treats it as new again — lets you test the full
RSS -> Telegram -> button flow on real data, without waiting for
actual news to break.

Usage:
    python scripts/force_test_item.py
    git add data/gezien.json && git commit -m "test: force one new item" && git push
    gh workflow run nieuwsbrief.yml
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEN_FILE = REPO_ROOT / "data" / "gezien.json"


def main() -> None:
    if not SEEN_FILE.exists():
        print("No data/gezien.json yet — nothing to un-mark.")
        sys.exit(1)

    with open(SEEN_FILE, encoding="utf-8") as f:
        seen = json.load(f)

    if not seen:
        print("data/gezien.json is empty already — everything already counts as new.")
        sys.exit(1)

    removed = seen.pop(0)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

    print(f"Un-marked one item — it will show up as new on the next run:\n  {removed}")


if __name__ == "__main__":
    main()
