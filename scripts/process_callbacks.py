"""
Poll Telegram for callback_query updates (button presses) since the
last run, mark the corresponding items as "write a blog post for this",
and give visible confirmation by swapping the button to a filled star.

Runs as its own step in .github/workflows/nieuwsbrief.yml, *before*
fetch_and_notify.py — matching the pipeline order in the project brief:
process button presses from last time first, then look for new RSS
items.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import telegram_api

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OFFSET_FILE = DATA_DIR / "telegram_offset.json"
ITEM_CACHE_FILE = DATA_DIR / "item_cache.json"
MARKED_FILE = DATA_DIR / "marked.json"

# Must match PENDING_BUTTON in fetch_and_notify.py — this is what a
# press changes the button *into*.
MARKED_BUTTON = "⭐ Marked for blog post"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    offset_state = load_json(OFFSET_FILE, {})
    offset = offset_state.get("offset")

    updates = telegram_api.get_updates(offset)
    print(f"Fetched {len(updates)} Telegram update(s) since last run.")

    if not updates:
        return

    item_cache = load_json(ITEM_CACHE_FILE, {})
    marked = load_json(MARKED_FILE, {})
    highest_update_id = (offset - 1) if offset else 0

    for update in updates:
        highest_update_id = max(highest_update_id, update["update_id"])
        callback = update.get("callback_query")
        if not callback:
            continue  # some other update type — ignore, still advance offset

        callback_id = callback["id"]
        sid = callback.get("data", "")
        message = callback.get("message") or {}
        message_id = message.get("message_id")

        if sid in marked:
            # Double-press (or a re-run that saw it again) — acknowledge
            # without re-editing or re-adding.
            telegram_api.answer_callback_query(callback_id, "Already marked ✅")
            continue

        item = item_cache.get(sid)
        if not item:
            telegram_api.answer_callback_query(
                callback_id,
                "Sorry — this one's too old, its details already expired from cache.",
            )
            continue

        marked[sid] = {**item, "marked_at": time.time(), "status": "pending"}
        print(f"  Marked for blog post: {item['title'][:60]}")

        if message_id is not None:
            telegram_api.edit_button(message_id, MARKED_BUTTON, sid)
        telegram_api.answer_callback_query(callback_id, "Marked for a blog post! 🌟")

    save_json(OFFSET_FILE, {"offset": highest_update_id + 1})
    save_json(MARKED_FILE, marked)
    pending = sum(1 for v in marked.values() if v.get("status") == "pending")
    print(f"{len(marked)} item(s) marked in total, {pending} still pending a blog post.")


if __name__ == "__main__":
    main()
