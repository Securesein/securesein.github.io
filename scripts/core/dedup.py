"""
Three layers of "have we already covered this?", in cost order.

**URL.** The same article is never worth two posts, at any age.

**Title.** Two feeds carry one story under different words, and a model
rewriting both converges them. Only applies inside a 7-day window,
because the same words a week apart are usually a duplicate and the
same words a year apart usually are not.

**Entity.** The one URL-level dedup cannot reach, and the highest-value
part of the Releases channel (brief §6.1 step 5). The News archive
already contains three separate posts about one GPT-6 Astra release —
`gpt-6-astra-a-new-era-for-developers`,
`gpt-6-astra-redefining-intelligence-…` and
`understanding-the-impact-of-gpt-6-astra-…` — from three different
URLs with three different headlines. Nothing short of keying on
(vendor, family, version, eventType) catches that.

The first two are lifted verbatim from generate_blog_post.py, thresholds
and stopword list included: they were tuned against the real archive
(they catch all three GPT-6 Astra posts and no other pair), and
re-deriving them would be a second change hiding inside a move.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from .constants import ENTITIES_FILE
from .state import read_json, write_json

# --- layers 1 and 2: url and title (moved, not changed) -------------

DEDUP_DAYS = 7
DEDUP_RULES = (
    # (minimum shared distinctive words, minimum containment)
    (3, 0.40),
    (2, 0.50),
)
DEDUP_SEQUENCE_RATIO = 0.72

TITLE_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for",
    "from", "how", "in", "into", "is", "it", "its", "new", "of", "on", "or",
    "s", "that", "the", "their", "this", "to", "what", "when", "who", "why",
    "will", "with", "you", "your", "inside", "exploring", "understanding",
    "unpacking", "navigating", "introducing", "look", "closer", "era",
}


def title_tokens(title: str) -> set[str]:
    """Distinctive words only. Single digits are kept deliberately —
    the "6" in "GPT-6 Astra" carries more of the story's identity than
    any other token in that headline."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {
        w for w in words
        if w not in TITLE_STOPWORDS and (len(w) > 1 or w.isdigit())
    }


def same_story(a: str, b: str) -> bool:
    ta, tb = title_tokens(a), title_tokens(b)
    if ta and tb:
        shared = len(ta & tb)
        containment = shared / min(len(ta), len(tb))
        for min_shared, min_containment in DEDUP_RULES:
            if shared >= min_shared and containment >= min_containment:
                return True
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= DEDUP_SEQUENCE_RATIO


def recent(posts: list[dict], days: int = DEDUP_DAYS) -> list[dict]:
    cutoff = date.today() - timedelta(days=days)
    out = []
    for post in posts:
        try:
            published = date.fromisoformat(post["pub_date"][:10])
        except ValueError:
            continue
        if published >= cutoff:
            out.append(post)
    return out


def is_duplicate(title: str, link: str | None, existing: list[dict]) -> bool:
    if link:
        for post in existing:
            if post["source_url"] and post["source_url"] == link:
                print(f"    Skipping — already covered in {post['slug']} "
                      f"(same source URL).", file=sys.stderr)
                return True

    for post in recent(existing):
        if same_story(title, post["title"]):
            print(f"    Skipping — too close to {post['slug']} "
                  f"(\"{post['title']}\"), published {post['pub_date']}.",
                  file=sys.stderr)
            return True
    return False


# --- layer 3: entity dedup ------------------------------------------

# Facts that make a second post about the same release worth writing —
# and even then as an UPDATE to the existing post rather than a new one.
MATERIAL_FACTS = ("ga_date", "pricing", "open_weights", "benchmark_claim", "deprecation")


@dataclass(frozen=True)
class EntityKey:
    vendor: str
    family: str
    version: str
    event_type: str

    def __str__(self) -> str:
        return f"{self.vendor}/{self.family}/{self.version or '-'}/{self.event_type}"


@dataclass
class Coverage:
    """What we already published about one entity."""

    key: str
    slug: str
    covered_at: str
    facts: list[str]


class EntityIndex:
    """state/entities.json — covered (vendor, family, version, eventType)
    keys plus a cooldown. Three outcomes, and the middle one is the
    interesting one:

      not seen                         -> publish
      seen, no material new fact       -> drop, reason "entity_covered"
      seen, WITH a material new fact   -> update the existing post
                                          (append a dated line, set
                                          updatedDate), consuming no
                                          budget and creating no new URL
    """

    def __init__(self, cooldown_days: int = 10, dry_run: bool = True):
        self.cooldown_days = cooldown_days
        self.dry_run = dry_run
        raw = read_json(ENTITIES_FILE, {"entities": {}})["entities"]
        self.entities: dict[str, Coverage] = {
            key: Coverage(key, row["slug"], row["coveredAt"], row.get("facts", []))
            for key, row in raw.items()
        }

    def _fresh(self, coverage: Coverage) -> bool:
        try:
            covered = datetime.fromisoformat(coverage.covered_at)
        except ValueError:
            return False
        if covered.tzinfo is None:
            covered = covered.replace(tzinfo=timezone.utc)
        return covered >= datetime.now(timezone.utc) - timedelta(days=self.cooldown_days)

    def lookup(self, key: EntityKey) -> Coverage | None:
        coverage = self.entities.get(str(key))
        if coverage is None or not self._fresh(coverage):
            return None
        return coverage

    def decide(self, key: EntityKey, new_facts: list[str]) -> tuple[str, Coverage | None]:
        """-> ("publish" | "update" | "drop", existing coverage)."""
        coverage = self.lookup(key)
        if coverage is None:
            return "publish", None
        unseen = [f for f in new_facts if f in MATERIAL_FACTS and f not in coverage.facts]
        if unseen:
            return "update", coverage
        return "drop", coverage

    def record(self, key: EntityKey, slug: str, facts: list[str]) -> None:
        existing = self.entities.get(str(key))
        merged = sorted(set(facts) | set(existing.facts if existing else []))
        self.entities[str(key)] = Coverage(
            str(key), slug, datetime.now(timezone.utc).isoformat(timespec="seconds"), merged
        )

    def save(self) -> None:
        if self.dry_run:
            print(
                f"    [dry-run] {len(self.entities)} entity key(s) held in memory; "
                f"state/entities.json left untouched."
            )
            return
        write_json(
            ENTITIES_FILE,
            {
                "entities": {
                    key: {
                        "slug": c.slug,
                        "coveredAt": c.covered_at,
                        "facts": c.facts,
                    }
                    for key, c in self.entities.items()
                }
            },
        )
