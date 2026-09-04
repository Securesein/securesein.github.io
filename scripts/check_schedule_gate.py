"""
Decides whether this workflow run should actually do work.

GitHub Actions' `schedule` trigger is not reliable — runs can be
delayed by a long margin or dropped entirely, especially around the
top of the hour when GitHub's infra is busy. Hand-picking exact UTC
cron times (even several per target, to cover DST) still means a
single dropped fire is a fully missed run.

So instead: nieuwsbrief.yml's cron fires every hour, all day, and this
script is the only thing that decides which of those firings actually
count — based on four generous daily windows (each ~2 hours wide) in
Europe/Amsterdam time. If the exact top-of-hour fire for a window gets
dropped, next hour's fire still lands inside the same window and
catches it. A tiny state file (data/schedule_state.json) remembers
which windows already ran today so a second fire in the same window
is a no-op, not a duplicate run.

Always says yes for a manual (workflow_dispatch) trigger.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "data" / "schedule_state.json"

# name -> (start hour inclusive, end hour exclusive), Europe/Amsterdam.
# Widen these if dropped fires ever cause a missed day; two hours has
# comfortable room for one dropped hourly fire in a row.
SLOTS = {
    "morning": (8, 10),
    "midday": (12, 14),
    "afternoon": (16, 18),
    "evening": (20, 22),
}


def current_slot(hour: int) -> str | None:
    for name, (start, end) in SLOTS.items():
        if start <= hour < end:
            return name
    return None


def main() -> None:
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        print("Manually triggered — always runs.")
        print("run=true")
        return

    now = datetime.now(ZoneInfo("Europe/Amsterdam"))
    today = now.date().isoformat()
    slot = current_slot(now.hour)

    if slot is None:
        print(f"It's {now:%H:%M} in Amsterdam — outside all four daily windows. Skipping.")
        print("run=false")
        return

    state = {}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if state.get("date") != today:
        state = {"date": today, "done": []}

    if slot in state["done"]:
        print(f"It's {now:%H:%M} in Amsterdam, in the '{slot}' window — already ran today. Skipping.")
        print("run=false")
        return

    state["done"].append(slot)
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"It's {now:%H:%M} in Amsterdam, in the '{slot}' window — this is a real run.")
    print("run=true")


if __name__ == "__main__":
    main()
