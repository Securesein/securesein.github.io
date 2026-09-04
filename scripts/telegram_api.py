"""Thin wrapper around the Telegram Bot HTTP API, shared by the
fetch/notify and callback-processing scripts so both talk to Telegram
the same way."""

from __future__ import annotations

import os
import sys

import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# A bot token is formatted "<bot_id>:<secret>" — the id half tells us
# which messages are *from this bot* without an extra getMe() call, so
# a reply can be checked against "is this actually replying to us".
BOT_ID = int(TELEGRAM_BOT_TOKEN.split(":")[0])


def _post(method: str, payload: dict) -> dict | None:
    try:
        response = requests.post(f"{API_BASE}/{method}", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"    Telegram {method} failed: {e}", file=sys.stderr)
        return None


def send_message(text: str) -> dict | None:
    """Plain message, no button — the only way to act on an article is
    to reply to it (see process_callbacks.py)."""
    return _post("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
    })


def send_reply(text: str, reply_to_message_id: int) -> dict | None:
    """Plain confirmation message, threaded under the user's reply."""
    return _post("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "reply_to_message_id": reply_to_message_id,
    })


def get_updates(offset: int | None) -> list[dict]:
    """Fetches pending updates since `offset` (no long-polling — this
    runs inside a scheduled job, not a live process, so we just want
    whatever's queued right now)."""
    payload = {"timeout": 0}
    if offset is not None:
        payload["offset"] = offset
    result = _post("getUpdates", payload)
    if not result or not result.get("ok"):
        return []
    return result.get("result", [])
