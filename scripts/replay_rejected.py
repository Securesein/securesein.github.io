#!/usr/bin/env python3
"""
Offer rejected items to a channel again, by un-marking them in the seen
cursor.

A rejection is normally final, and should be: an item dropped for being
a customer story will still be a customer story next run, and retrying
it burns a model call to be told so again. What is NOT fine is a
rejection that was the pipeline's fault. In October the release draft
prompt demanded a version-over-version comparison and returned
"insufficient" without one, which dropped thirty genuine launches —
Mistral Large 4, Claude Haiku 5.5, EmbeddingGemma 2 among them. The
prompt was fixed; the items were gone. Their ids were in the seen
cursor, and state/rejected.jsonl recorded a url while the feeds key on
guid, so there was nothing to match on.

reject() now records `itemId`, and this reads it back. Items rejected
before that change have `itemId: null` and cannot be replayed; that is
a one-off loss, not a permanent property.

    # what would be replayed, and why — this is the default
    python3 scripts/replay_rejected.py --reason no_product_angle --since 2026-10-06

    # actually un-mark them
    python3 scripts/replay_rejected.py --reason no_product_angle --since 2026-10-06 --write

Then commit state/seen_releases.json and let the channel run; the items
are ingested as new and go through the whole pipeline again, including
every gate. Nothing here publishes anything.

Note the age filter in the channel itself (`max_item_age_days`,
14 by default): replaying something older than that will re-ingest it
only for it to be dropped again as stale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.constants import REJECTED_FILE, SEEN_RELEASES_FILE  # noqa: E402


def _rejections() -> list[dict]:
    if not REJECTED_FILE.exists():
        return []
    rows = []
    for line in REJECTED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reason", action="append", default=[],
                    help="rejection reason to replay; repeatable")
    ap.add_argument("--since", default="",
                    help="only rejections at or after this date (YYYY-MM-DD)")
    ap.add_argument("--channel", default="",
                    help="limit to one channel, e.g. releases")
    ap.add_argument("--url", action="append", default=[],
                    help="replay one specific url; repeatable")
    # NOT --apply. test_learning bans that flag name everywhere under
    # scripts/, because §11.3's rule is that Scout proposes and the
    # owner approves — the ban is blunt on purpose so the rule cannot be
    # sidestepped by adding an --apply somewhere it looks harmless. This
    # writes a cursor, not the interest profile, but the guard is worth
    # more than the nicer word.
    ap.add_argument("--write", action="store_true",
                    help="write the cursor (default is to report only)")
    args = ap.parse_args()

    if not (args.reason or args.url):
        ap.error("give at least one --reason or --url, so this cannot "
                 "accidentally replay the whole log")

    rows = [
        r for r in _rejections()
        if (not args.reason or r.get("reason") in args.reason)
        and (not args.channel or r.get("channel") == args.channel)
        and (not args.since or str(r.get("at", ""))[:10] >= args.since)
        and (not args.url or r.get("url") in args.url)
    ]
    if not rows:
        print("Nothing in state/rejected.jsonl matches those filters.")
        return 0

    replayable = {r["itemId"]: r for r in rows if r.get("itemId")}
    lost = [r for r in rows if not r.get("itemId")]

    cursor = json.loads(SEEN_RELEASES_FILE.read_text(encoding="utf-8"))
    seen = cursor.get("ids", [])
    present = [i for i in replayable if i in seen]
    absent = [i for i in replayable if i not in seen]

    print(f"{len(rows)} matching rejection(s).")
    if lost:
        print(f"  {len(lost)} with no itemId — rejected before reject() "
              f"recorded one, and not replayable:")
        for r in lost[:10]:
            print(f"      {str(r.get('at',''))[:10]}  {r.get('title','')[:68]}")
        if len(lost) > 10:
            print(f"      ... and {len(lost) - 10} more")
    if absent:
        print(f"  {len(absent)} already absent from the cursor — nothing to do.")
    if not present:
        print("Nothing to un-mark.")
        return 0

    print(f"  {len(present)} would be offered again:")
    for i in present:
        r = replayable[i]
        print(f"      {str(r.get('at',''))[:10]}  {r.get('title','')[:68]}")

    if not args.write:
        print("\nReport only. Re-run with --write to write the cursor.")
        return 0

    cursor["ids"] = [i for i in seen if i not in set(present)]
    SEEN_RELEASES_FILE.write_text(
        json.dumps(cursor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nUn-marked {len(present)} item(s) in {SEEN_RELEASES_FILE.name}. "
          f"Commit it, then run the channel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
