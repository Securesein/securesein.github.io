#!/usr/bin/env python3
"""
Summarise state/raw_feed_ratings.jsonl for hand-tuning
config/papers_profile.yaml. Never writes to the profile itself — see
that file's own header on why Reader stays hand-tuned rather than
learning automatically, and rate.py's docstring on how this data
gets collected in the first place.

    python scripts/papers/rating_report.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RATINGS_FILE = REPO_ROOT / "state" / "raw_feed_ratings.jsonl"


def load_ratings() -> list[dict]:
    if not RATINGS_FILE.exists():
        return []
    rows = []
    for line in RATINGS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def by_bucket(rows: list[dict]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        out[row.get("bucket") or "unmatched"].append(row["rating"])
    return out


def render(rows: list[dict]) -> str:
    if not rows:
        return ("No ratings yet. Nothing to report until raw_feed.py has been "
                "sent and rated at least a few times.")

    lines = [f"{len(rows)} rating(s) recorded.", ""]

    lines.append("By bucket (higher average = the profile is under-weighting it;")
    lines.append("'unmatched' rated high = a real blind spot, worth a new keyword):")
    grouped = by_bucket(rows)
    for bucket, ratings in sorted(grouped.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        avg = sum(ratings) / len(ratings)
        lines.append(f"  {bucket:<16} avg {avg:.2f}  (n={len(ratings)})  {ratings}")

    lines.append("")
    lines.append("Highest-rated unmatched items (candidates for a new keyword):")
    unmatched_hits = sorted(
        (r for r in rows if not r.get("bucket") and r["rating"] >= 4),
        key=lambda r: -r["rating"],
    )
    if unmatched_hits:
        for r in unmatched_hits[:10]:
            lines.append(f"  [{r['rating']}/5] {r['title']}")
    else:
        lines.append("  (none rated 4 or 5 yet)")

    lines.append("")
    lines.append("Lowest-rated matched items (candidates for weight down / an exclude phrase):")
    matched_misses = sorted(
        (r for r in rows if r.get("bucket") and r["rating"] <= 2),
        key=lambda r: r["rating"],
    )
    if matched_misses:
        for r in matched_misses[:10]:
            lines.append(f"  [{r['rating']}/5] ({r['bucket']}) {r['title']}")
    else:
        lines.append("  (none rated 1 or 2 yet)")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    print(render(load_ratings()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
