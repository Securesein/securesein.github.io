"""
Poll Telegram for messages since the last run and turn them into blog
post requests, in two ways:

- a reply to one of our article messages: marks that article for a
  post. The reply text (if any) becomes "instructions" — free-form
  guidance for how to write it (e.g. "focus on pricing", "spend more
  time on the security angle"). An empty reply just means full
  creative freedom under the usual voice/structure rules. Confirmed
  with a threaded reply. Multiple replies to the same article each
  queue their own post, so different angles can be requested over time.
- a plain message, not a reply to anything: marks a *custom* post with
  no source article at all — the message text becomes the brief,
  verbatim.

There is no button — a reply is the only way to act on an article.

Runs as its own step in .github/workflows/nieuwsbrief.yml, *before*
fetch_and_notify.py — matching the pipeline order in the project brief:
process messages from last time first, then look for new RSS items.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import telegram_api

# Telegram can't send a truly empty message, so "no instructions,
# just do your best" tends to show up as one of these placeholders —
# treat them the same as an empty reply instead of literally as an
# instruction (an LLM told to focus on "empty" would get confused).
NO_INSTRUCTION_PLACEHOLDERS = {
    "empty", "leeg", "none", "n/a", "na", "-", ".", "geen", "niks", "nvt",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OFFSET_FILE = DATA_DIR / "telegram_offset.json"
ITEM_CACHE_FILE = DATA_DIR / "item_cache.json"
MARKED_FILE = DATA_DIR / "marked.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def handle_article_reply(message: dict, item_cache: dict, marked: dict, msgid_to_sid: dict) -> None:
    reply_to = message["reply_to_message"]
    if reply_to.get("from", {}).get("id") != telegram_api.BOT_ID:
        return  # replying to something other than one of our article messages

    sid = msgid_to_sid.get(reply_to.get("message_id"))
    item = item_cache.get(sid) if sid else None
    if not item:
        telegram_api.send_reply(
            "Sorry — this one's too old, its details already expired from cache.",
            message["message_id"],
        )
        return

    instructions = (message.get("text") or "").strip() or None
    if instructions and instructions.strip(" .!").lower() in NO_INSTRUCTION_PLACEHOLDERS:
        instructions = None
    key = f"{sid}:{message['message_id']}"
    marked[key] = {
        **item,
        "instructions": instructions,
        "kind": "article",
        "marked_at": time.time(),
        "status": "pending",
    }

    if instructions:
        print(f"  Marked for a blog post — focus: \"{instructions}\" ({item['title'][:50]})")
        confirm = f"Got it — queued a post about this article, focusing on: “{instructions}”. 📝"
    else:
        print(f"  Marked for a blog post (no specific instructions): {item['title'][:60]}")
        confirm = "Got it — queued a post about this article. 📝"
    telegram_api.send_reply(confirm, message["message_id"])


def handle_custom_request(message: dict, marked: dict) -> None:
    """A plain message, not a reply to anything — the user's own
    words, with no article attached. The whole message becomes the
    brief, verbatim."""
    brief = (message.get("text") or "").strip()
    if not brief:
        return  # e.g. a photo/sticker with no caption — nothing to act on

    key = f"custom:{message['message_id']}"
    marked[key] = {
        "brief": brief,
        "kind": "custom",
        "marked_at": time.time(),
        "status": "pending",
    }
    preview = brief if len(brief) <= 80 else brief[:79] + "…"
    print(f"  Marked custom post: \"{preview}\"")
    telegram_api.send_reply(f"Got it — queued a post: “{preview}”. 📝", message["message_id"])


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

        message = update.get("message")
        if not message or message.get("from", {}).get("is_bot"):
            continue  # not a message, or one of our own — ignore, still advance offset

        if message.get("reply_to_message"):
            handle_article_reply(message, item_cache, marked, msgid_to_sid)
        else:
            handle_custom_request(message, marked)

    save_json(OFFSET_FILE, {"offset": highest_update_id + 1})
    save_json(MARKED_FILE, marked)
    pending = sum(1 for v in marked.values() if v.get("status") == "pending")
    print(f"{len(marked)} item(s) marked in total, {pending} still pending a blog post.")


if __name__ == "__main__":
    main()
