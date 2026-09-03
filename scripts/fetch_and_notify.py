"""
Fetch new AI-news RSS items, summarize each with OpenAI, and send it to
Telegram with a "Write blog post" button attached.

Run via GitHub Actions (workflow_dispatch for now, cron later — see
.github/workflows/nieuwsbrief.yml). State lives in JSON files under
data/, which the workflow commits back to the repo after this script
runs, so re-running never sends the same item twice.

On the very first run (no data/gezien.json yet) this only records a
baseline of what's currently in the feeds and sends nothing — otherwise
adding 29 feeds for the first time would flood Telegram with everything
they've ever published.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

import telegram_api

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = REPO_ROOT / "feeds.json"
DATA_DIR = REPO_ROOT / "data"
SEEN_FILE = DATA_DIR / "gezien.json"
ITEM_CACHE_FILE = DATA_DIR / "item_cache.json"

# Empty star until pressed — process_callbacks.py swaps it to a filled,
# gold star on click so a press is unmistakable at a glance.
PENDING_BUTTON = "☆ Write blog post"

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
# Kept as an env var (not hardcoded) so a deprecated/renamed model doesn't
# require a code change — just update the workflow env.
SUMMARY_MODEL = os.environ.get("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")

# Ceiling per run so a long gap between runs can't dump a flood of
# messages into Telegram all at once.
MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN", "15"))
ITEMS_PER_FEED_CHECK = 10
ARTICLE_MAX_CHARS = 3000
ARTICLE_FETCH_TIMEOUT = 15
ITEM_CACHE_RETENTION_DAYS = 14

client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# State: feeds.json (read-only input) and data/*.json (read + write)
# ---------------------------------------------------------------------------

def load_feeds() -> list[dict]:
    with open(FEEDS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_seen() -> tuple[set[str], bool]:
    """Returns (seen item IDs, is_first_run)."""
    if not SEEN_FILE.exists():
        return set(), True
    with open(SEEN_FILE, encoding="utf-8") as f:
        return set(json.load(f)), False


def save_seen(seen_ids: set[str]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_ids), f, ensure_ascii=False, indent=2)


def load_item_cache() -> dict:
    if not ITEM_CACHE_FILE.exists():
        return {}
    with open(ITEM_CACHE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_item_cache(cache: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(ITEM_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def prune_item_cache(cache: dict) -> dict:
    """Drops entries older than ITEM_CACHE_RETENTION_DAYS so this file
    doesn't grow forever — a late button press beyond that window just
    won't resolve to an item anymore."""
    cutoff = time.time() - ITEM_CACHE_RETENTION_DAYS * 86400
    return {k: v for k, v in cache.items() if v.get("cached_at", 0) >= cutoff}


def item_id(entry) -> str:
    """Stable unique ID for an RSS item: guid if present, else the link."""
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def short_id(full_id: str) -> str:
    """Telegram callback_data is capped at 64 bytes, and RSS guids/links
    routinely exceed that — so buttons carry this short hash instead, and
    item_cache.json maps it back to the real item (title/link/source)."""
    return hashlib.sha256(full_id.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Fetching new items
# ---------------------------------------------------------------------------

def fetch_new_items(feeds: list[dict], seen_ids: set[str]) -> list[dict]:
    """Round-robins across feeds so one prolific feed can't crowd out
    the others, capped at MAX_ITEMS_PER_RUN."""
    per_feed_new = []
    for feed in feeds:
        parsed = feedparser.parse(feed["url"])
        new_in_feed = []
        for entry in parsed.entries[:ITEMS_PER_FEED_CHECK]:
            eid = item_id(entry)
            if eid in seen_ids:
                continue
            new_in_feed.append({
                "id": eid,
                "title": entry.get("title", "(no title)"),
                "rss_summary": entry.get("summary", "")[:500],
                "link": entry.get("link", ""),
                "source": feed["naam"],
            })
        per_feed_new.append(new_in_feed)

    items = []
    while len(items) < MAX_ITEMS_PER_RUN and any(per_feed_new):
        for feed_items in per_feed_new:
            if feed_items:
                items.append(feed_items.pop(0))
                if len(items) >= MAX_ITEMS_PER_RUN:
                    break
    return items


def fetch_article_text(url: str) -> str:
    """Best-effort plain-text scrape. Returns "" on any failure so
    callers fall back to the RSS summary instead of crashing the run."""
    if not url:
        return ""
    try:
        response = requests.get(
            url,
            timeout=ARTICLE_FETCH_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; securesein-pipeline/1.0)"},
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:ARTICLE_MAX_CHARS]


# ---------------------------------------------------------------------------
# Summarizing
# ---------------------------------------------------------------------------

def summarize_item(item: dict) -> str:
    article_text = fetch_article_text(item["link"])
    source_text = article_text if len(article_text) >= 200 else item["rss_summary"]

    if len(source_text) < 50:
        return "(no summary available — see link for the full article)"

    prompt = f"""Below is the (possibly truncated) text of a news article
titled "{item['title']}".

Text:
{source_text}

Write a short, factual summary in exactly 2 sentences: what was
announced or happened, with concrete details where possible (numbers,
names, what's new about a product/model).

Do not explain why this matters or who it's relevant for. No preamble
like "here is a summary". Return ONLY the summary text, nothing else."""

    try:
        response = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        summary = (response.choices[0].message.content or "").strip()
        return summary or "(no summary available — see link for the full article)"
    except Exception as e:
        print(f"    OpenAI summarization failed: {e}", file=sys.stderr)
        return "(no summary available — see link for the full article)"


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def notify_telegram(item: dict, summary: str, sid: str) -> bool:
    text = f"📰 {item['title']}\n({item['source']})\n\n{summary}\n\n{item['link']}"
    result = telegram_api.send_message(text, PENDING_BUTTON, sid)
    return result is not None and result.get("ok", False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    feeds = load_feeds()
    print(f"Loaded {len(feeds)} feeds from {FEEDS_FILE.name}.")

    seen_ids, is_first_run = load_seen()
    item_cache = prune_item_cache(load_item_cache())

    if is_first_run:
        print("First run: recording baseline only, nothing will be sent...")
        for feed in feeds:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:ITEMS_PER_FEED_CHECK]:
                seen_ids.add(item_id(entry))
        save_seen(seen_ids)
        save_item_cache(item_cache)
        print(f"Baseline saved ({len(seen_ids)} items). Future runs will only "
              f"pick up items that are genuinely new.")
        return

    print("Looking for new items...")
    new_items = fetch_new_items(feeds, seen_ids)
    print(f"  {len(new_items)} new item(s) found.")

    if not new_items:
        print("Nothing new this time.")
        save_item_cache(item_cache)  # still persist any pruning
        return

    for item in new_items:
        print(f"  Summarizing: {item['title'][:60]}...")
        summary = summarize_item(item)
        sid = short_id(item["id"])

        sent = notify_telegram(item, summary, sid)
        # Only mark as seen (and cache it) once it's actually been sent —
        # otherwise a failed Telegram send would silently drop the item
        # instead of retrying it on the next run.
        if sent:
            seen_ids.add(item["id"])
            item_cache[sid] = {
                "title": item["title"],
                "link": item["link"],
                "source": item["source"],
                "cached_at": time.time(),
            }
            save_seen(seen_ids)
            save_item_cache(item_cache)
        time.sleep(1)  # be nice to Telegram's rate limit

    print("Done.")


def send_test_message() -> bool:
    """Sends one fixed test item through the real summarize + send path
    (OpenAI included), independent of feed/state — to verify the wiring
    without waiting for real news."""
    print("Sending test message (exercises OpenAI + Telegram)...")
    test_item = {
        "id": "test",
        "title": "Pipeline test",
        "rss_summary": (
            "This is a fixed test snippet used to verify the pipeline's "
            "OpenAI summarization step during setup. Anthropic released "
            "a faster, cheaper reasoning model in 2026 aimed at "
            "everyday agentic workloads, lowering cost and latency for "
            "teams running agents in production."
        ),
        "link": "",
        "source": "fetch_and_notify.py --test",
    }
    summary = summarize_item(test_item)
    ok = notify_telegram(test_item, summary, short_id("test"))
    print("OK!" if ok else "Failed — see error above.")
    return ok


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(0 if send_test_message() else 1)
    main()
