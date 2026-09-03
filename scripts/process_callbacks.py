"""
Poll Telegram for updates since the last run and turn them into blog
post requests, in two ways:

- callback_query (the ☆ button): marks the article itself for a post —
  a direct write-up of that specific news item. Confirmed by swapping
  the button to a filled star.
- a plain reply to one of our messages: marks a *concept* post — the
  reply text is the topic (e.g. "multimodality"), the article is only
  background/reference, not the subject. Confirmed with a threaded
  reply. Both can exist for the same article at once.

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


def handle_button_press(callback: dict, item_cache: dict, marked: dict) -> None:
    callback_id = callback["id"]
    sid = callback.get("data", "")
    message = callback.get("message") or {}
    message_id = message.get("message_id")

    if sid in marked:
        # Double-press (or a re-run that saw it again) — acknowledge
        # without re-editing or re-adding.
        telegram_api.answer_callback_query(callback_id, "Already marked ✅")
        return

    item = item_cache.get(sid)
    if not item:
        telegram_api.answer_callback_query(
            callback_id,
            "Sorry — this one's too old, its details already expired from cache.",
        )
        return

    marked[sid] = {**item, "kind": "article", "marked_at": time.time(), "status": "pending"}
    print(f"  Marked article for a blog post: {item['title'][:60]}")

    if message_id is not None:
        telegram_api.edit_button(message_id, MARKED_BUTTON, sid)
    telegram_api.answer_callback_query(callback_id, "Marked for a blog post! 🌟")


def handle_reply(message: dict, item_cache: dict, marked: dict, msgid_to_sid: dict) -> None:
    reply_to = message.get("reply_to_message")
    if not reply_to or reply_to.get("from", {}).get("id") != telegram_api.BOT_ID:
        return  # not a reply, or replying to something other than us

    topic = (message.get("text") or "").strip()
    if not topic:
        return  # e.g. a reply that's a photo/sticker with no text — nothing to act on

    sid = msgid_to_sid.get(reply_to.get("message_id"))
    item = item_cache.get(sid) if sid else None
    if not item:
        telegram_api.send_reply(
            "Sorry — this one's too old, its details already expired from cache.",
            message["message_id"],
        )
        return

    concept_key = f"{sid}:concept:{message['message_id']}"
    marked[concept_key] = {
        **item,
        "topic": topic,
        "kind": "concept",
        "marked_at": time.time(),
        "status": "pending",
    }
    print(f"  Marked concept post: \"{topic}\" (from: {item['title'][:60]})")
    telegram_api.send_reply(
        f"Got it — queued a post about “{topic}”, using this article as reference. 📝",
        message["message_id"],
    )


def main() -> None:
    offset_state = load_json(OFFSET_FILE, {})
    offset = offset_state.get("offset")

    updates = telegram_api.get_updates(offset)
    print(f"Fetched {len(updates)} Telegram update(s) since last run.")

    if not updates:
        return

    item_cache = load_json(ITEM_CACHE_FILE, {})
    marked = load_json(MARKED_FILE, {})
    msgid_to_sid = {v["message_id"]: k for k, v in item_cache.items() if "message_id" in v}
    highest_update_id = (offset - 1) if offset else 0

    for update in updates:
        highest_update_id = max(highest_update_id, update["update_id"])

        callback = update.get("callback_query")
        message = update.get("message")
        if callback:
            handle_button_press(callback, item_cache, marked)
        elif message:
            handle_reply(message, item_cache, marked, msgid_to_sid)
        # anything else (edited messages, other update types) — ignore,
        # still advance the offset past it

    save_json(OFFSET_FILE, {"offset": highest_update_id + 1})
    save_json(MARKED_FILE, marked)
    pending = sum(1 for v in marked.values() if v.get("status") == "pending")
    print(f"{len(marked)} item(s) marked in total, {pending} still pending a blog post.")


if __name__ == "__main__":
    main()
