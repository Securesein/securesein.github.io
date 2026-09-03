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


def send_message(text: str, button_text: str, button_callback_data: str) -> dict | None:
    return _post("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": button_text, "callback_data": button_callback_data}
            ]]
        },
    })


def edit_button(message_id: int, button_text: str, button_callback_data: str) -> dict | None:
    """Swaps the inline button's label in place — used to visibly
    confirm a press (e.g. the star turning solid/gold) without
    touching the message text."""
    return _post("editMessageReplyMarkup", {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": button_text, "callback_data": button_callback_data}
            ]]
        },
    })


def send_reply(text: str, reply_to_message_id: int) -> dict | None:
    """Plain confirmation message, threaded under the user's reply —
    no button, unlike send_message()."""
    return _post("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "reply_to_message_id": reply_to_message_id,
    })


def answer_callback_query(callback_query_id: str, text: str = "") -> dict | None:
    """Stops the loading spinner on the pressed button. Telegram expects
    this after every callback_query, whether or not we act on it."""
    return _post("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
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
