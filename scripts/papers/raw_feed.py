#!/usr/bin/env python3
"""
Raw research feed (build brief §9, extended) — a second, much less
filtered Telegram stream, for rating rather than reading.

    python scripts/papers/raw_feed.py            [--dry-run] (default)
    python scripts/papers/raw_feed.py --publish   (actually sends to Telegram)

The normal digest (run.py) filters hard before anything reaches you: a
keyword prefilter, then an LLM triage, then a top-6-to-12 cut. That is
right for a thing you read every day, and wrong for the one question
this script exists to answer — "is the filter itself any good?" — since
a filter can only be judged against the things it rejected too.

So this sends a wider batch with NO LLM call at all (rating is cheap
enough not to need one, and the whole point is to sample past the
keyword filter, not through it): a handful of the highest keyword-scoring
matched candidates (to calibrate weight on buckets it already favours),
and a handful of genuinely-unmatched ones chosen at random (to surface
keywords or subjects the profile has no bucket for yet). Every message
carries five number buttons; a tap is recorded by telegram/rate.py,
which scripts/run.py --feedback polls for on the same schedule as the
main digest's reaction buttons (see that module's docstring for why this
shares a poller instead of running its own).

Same disposability as Reader Phase 1: no persistent dedup, no state
written by this script itself (only the rating side writes state) — an
occasional repeat costs nothing at this volume.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from papers.rate import callback_data  # noqa: E402
from papers.run import (  # noqa: E402
    dedup,
    drop_non_new,
    fetch_feed,
    keyword_score,
    load_profile,
)
from telegram import api  # noqa: E402

MATCHED_CAP = 10
UNMATCHED_SAMPLE = 5
ABSTRACT_CHARS = 320


def score_all(items: list[dict], profile: dict) -> tuple[list[dict], list[dict]]:
    """Every genuinely-new item, scored — split into what matched a
    bucket and what didn't, unlike keyword_prefilter (papers/run.py),
    which throws the unmatched half away. That half is exactly what
    this script exists to sample from."""
    matched, unmatched = [], []
    for item in items:
        score, bucket = keyword_score(item, profile)
        scored = {**item, "keyword_score": score, "bucket": bucket}
        (matched if score > 0 and bucket else unmatched).append(scored)
    matched.sort(key=lambda i: i["keyword_score"], reverse=True)
    return matched, unmatched


def select_batch(matched: list[dict], unmatched: list[dict],
                  *, matched_cap: int = MATCHED_CAP,
                  unmatched_sample: int = UNMATCHED_SAMPLE,
                  rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random()
    picks = matched[:matched_cap]
    pool = unmatched[:]
    rng.shuffle(pool)
    picks += pool[:unmatched_sample]
    return picks


def render(item: dict) -> str:
    tag = f"{item['bucket']} · {item['keyword_score']:.1f}" if item.get("bucket") else "unmatched"
    abstract = item["abstract"][:ABSTRACT_CHARS]
    if len(item["abstract"]) > ABSTRACT_CHARS:
        abstract = abstract.rsplit(" ", 1)[0] + "…"
    return (
        f"{item['title']}\n"
        f"[{tag}]\n\n"
        f"{abstract}\n\n"
        f"arxiv.org/abs/{item['id']}"
    )


def rating_keyboard(item_id: str) -> list[list[dict]]:
    return [[
        {"text": str(n), "callback_data": callback_data(n, item_id)}
        for n in range(1, 6)
    ]]


def send(item: dict) -> bool:
    result = api.send(render(item), keyboard=rating_keyboard(item["id"]))
    return bool(result and result.get("ok"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_true", default=None)
    group.add_argument("--publish", dest="dry_run", action="store_false")
    args = parser.parse_args(argv)
    dry_run = True if args.dry_run is None else args.dry_run

    print("Raw research feed — " + ("DRY RUN, nothing will be sent" if dry_run else "PUBLISHING FOR REAL"))

    profile = load_profile()
    raw = fetch_feed()
    print(f"  fetched {len(raw)} raw entries")
    items = drop_non_new(dedup(raw))
    print(f"  {len(items)} genuinely new/cross after dedup")

    matched, unmatched = score_all(items, profile)
    print(f"  {len(matched)} match a bucket, {len(unmatched)} match none")

    batch = select_batch(matched, unmatched)
    print(f"  sending {len(batch)} for rating "
          f"({min(len(matched), MATCHED_CAP)} matched, "
          f"{len(batch) - min(len(matched), MATCHED_CAP)} unmatched sample)")

    if dry_run:
        print()
        for item in batch:
            print(render(item))
            print("-" * 40)
        print("[dry-run] not sent. Re-run with --publish to send for real.")
        return 0

    print("Sending to Telegram...")
    sent = sum(send(item) for item in batch)
    print(f"sent {sent}/{len(batch)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
