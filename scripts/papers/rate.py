"""
Ratings for the raw research feed (build brief §9, extended).

Reader's normal digest already filters and ranks before anything reaches
Telegram — by the time you see the top 6-12, a lot of judgement has
already been made *for* you. This is the opposite signal: a broader,
less-filtered sample (raw_feed.py), each item with five number buttons,
so you can rate things the keyword/LLM funnel would never have shown you
at all. The point is not to gate anything automatically — see
config/papers_profile.yaml's own header on why Reader stays hand-tuned —
it is to build up state/raw_feed_ratings.jsonl as real evidence for
deciding *by hand* which keywords or buckets are worth adjusting.
`rating_report.py` reads that file back and summarises it for exactly
that read, never writes to the profile itself.

Deliberately separate from telegram/feedback.py rather than added to its
ACTIONS table: that module's whole shape assumes a Radar entry exists
for the thing being reacted to (radar.find(item_id)), because it is
scoped to published posts. A rating here is about an arXiv id that was
never published and never will be — forcing it through apply()'s
Radar lookup would mean either a fake Radar entry or an exception path
that only exists to be silenced. The two are wired into the SAME
Telegram poll in scripts/run.py's --feedback handler (one getUpdates
call, both modules independently pick out the callback shapes they
recognise) rather than each running their own poller: getUpdates is
destructive and scoped to the whole bot token, so a second independent
poller would race the existing one for the same updates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RATINGS_FILE = REPO_ROOT / "state" / "raw_feed_ratings.jsonl"

PREFIX = "rr"  # "raw research" — kept short, callback_data has a 64-byte cap
VALID_SCORES = {1, 2, 3, 4, 5}


def callback_data(score: int, item_id: str) -> str:
    return f"{PREFIX}:{score}:{item_id}"


def parse_callback(data: str) -> tuple[int, str] | None:
    """"rr:<score>:<id>" -> (score, id), or None for anything else —
    including every callback_data shape telegram/feedback.py owns."""
    if not data or not data.startswith(f"{PREFIX}:"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    _, score_s, item_id = parts
    if not score_s.isdigit() or not item_id:
        return None
    score = int(score_s)
    if score not in VALID_SCORES:
        return None
    return score, item_id


def record(score: int, item_id: str, *, title: str, bucket: str | None,
           keyword_score: float, dry_run: bool = True) -> None:
    """Append one rating. Never rewritten, same discipline as
    state/feedback.jsonl — the report aggregates on read."""
    if dry_run:
        return
    RATINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "id": item_id,
        "title": title,
        "bucket": bucket,
        "keywordScore": keyword_score,
        "rating": score,
    }
    with RATINGS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def handle_updates(updates: list[dict], *, dry_run: bool = True) -> list[dict]:
    """Mirrors telegram/feedback.py's handle_updates shape (a list of
    outcomes scripts/run.py can print) but only ever touches callback
    data this module owns — see the module docstring for why the two
    don't share a code path."""
    outcomes = []
    for update in updates:
        query = update.get("callback_query")
        if not query:
            continue
        parsed = parse_callback(query.get("data", ""))
        if parsed is None:
            continue
        score, item_id = parsed
        # The item's own title/bucket/keyword_score travel inside the
        # callback_data's sibling message rather than a lookup, because
        # there is no Radar (or any other store) that remembers raw,
        # never-published candidates — see raw_feed.py's render(), which
        # packs them into the message text this reads back out of.
        message = query.get("message", {})
        title, bucket, keyword_score = _unpack_message(message.get("text", ""))
        record(score, item_id, title=title, bucket=bucket,
               keyword_score=keyword_score, dry_run=dry_run)
        outcomes.append({
            "id": item_id, "rating": score, "accepted": True,
            "detail": f"recorded {score}/5",
        })
        if not dry_run:
            from telegram import api

            api.answer_callback(query.get("id", ""), f"Rated {score}/5")
    return outcomes


def _unpack_message(text: str) -> tuple[str, str | None, float]:
    """raw_feed.py's render() always puts the title on the first line and
    a "[bucket · score X.X]" tag on the second — parsed back out here
    rather than carried in a second lookup table, so a rating never fails
    just because state was cleared between sending and tapping."""
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    bucket = None
    keyword_score = 0.0
    if len(lines) > 1:
        tag = lines[1].strip("[] \n")
        if "·" in tag:
            cat, _, score_part = tag.partition("·")
            bucket = cat.strip() or None
            try:
                keyword_score = float(score_part.split()[-1])
            except (ValueError, IndexError):
                pass
    return title, bucket, keyword_score
