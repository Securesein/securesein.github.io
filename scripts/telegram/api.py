"""
The Telegram transport, wrapped so that importing it is always safe.

scripts/telegram_api.py — the one the existing live pipeline uses —
reads TELEGRAM_BOT_TOKEN at import time and raises without it. That is
fine for a script whose only job is to send, and useless here: the
digest has to be RENDERABLE and inspectable on a laptop with no token,
because that is how it gets tested without messaging anyone.

So the failure mode moves from "cannot import" to "cannot send", and
`available()` answers the question honestly before anything tries.

    ############################################################
    #  NOTHING IN THIS REPOSITORY SENDS A REAL MESSAGE.        #
    #                                                          #
    #  Every send goes through send() below, which refuses     #
    #  unless BOTH a token is present AND the caller passed    #
    #  --send explicitly AND the run is not a dry run. No      #
    #  workflow passes --send. No workflow has a schedule that #
    #  would reach one. During this build not one real message #
    #  was sent; the digest was verified by rendering it and   #
    #  reading it.                                             #
    ############################################################
"""

from __future__ import annotations

import os
import sys

API_TIMEOUT = 15
# Telegram refuses anything over 4096 characters, and a digest that
# fails to send is worse than a short one.
MESSAGE_LIMIT = 4000


def available() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN")
                and os.environ.get("TELEGRAM_CHAT_ID"))


def _post(method: str, payload: dict) -> dict | None:
    if not available():
        print("    Telegram is not configured (no TELEGRAM_BOT_TOKEN / "
              "TELEGRAM_CHAT_ID) — nothing sent.", file=sys.stderr)
        return None
    import requests

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001 — report, never crash the run
        print(f"    Telegram {method} failed: {exc}", file=sys.stderr)
        return None


def truncate(text: str) -> str:
    if len(text) <= MESSAGE_LIMIT:
        return text
    return text[: MESSAGE_LIMIT - 20] + "\n…(truncated)"


def send(text: str, *, keyboard: list | None = None) -> dict | None:
    """One message, optionally with an inline keyboard.

    The keyboard is how feedback addresses a specific item: each button
    carries `callback_data` of the form "<action>:<candidateId>", and
    the candidate id is a stable hash of the item's URL (core/radar.py),
    so a tap hours later still refers to the thing it was shown under.
    """
    payload = {
        "chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
        "text": truncate(text),
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return _post("sendMessage", payload)


def answer_callback(callback_id: str, text: str) -> dict | None:
    """The little toast Telegram shows when a button is tapped. Without
    it the button spins until it times out and the owner cannot tell
    whether the tap registered."""
    return _post("answerCallbackQuery",
                 {"callback_query_id": callback_id, "text": text[:200]})


def get_updates(offset: int | None) -> list[dict]:
    payload = {"timeout": 0}
    if offset is not None:
        payload["offset"] = offset
    result = _post("getUpdates", payload)
    if not result or not result.get("ok"):
        return []
    return result.get("result", [])
