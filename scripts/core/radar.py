"""
The Radar (brief §6) — everything that passed the quality gate and lost
on ranking.

**Nothing good is thrown away, but almost nothing becomes a post.** That
is the structural answer to A1: 30-50 items a day land here at the cost
of one cheap classification call each, and ~3 a day become posts. An
item here stays eligible for promotion later — a Radar item that gets a
⭐ in the digest, or that becomes newly relevant when a related item
appears, can be written up days after it was first seen.

DECISION A3: INTERNAL ONLY. The collection exists, is validated by the
same Zod schema that guards posts, and feeds the Telegram digest. There
is deliberately NO /radar/ public route, no navigation entry, no RSS and
no sitemap presence. §6.2's alternative, taken as written.

STORAGE. One JSON file per month (`src/content/radar/2026-09.json`),
each holding an array, rather than one file per item: §6.1 allows either
and at 30-50 items a day the per-item version would put ~15,000 files in
the content directory within a year and make every Astro build slower
for nothing.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .constants import RADAR_COLLECTION_DIR
from .state import now_iso, read_json, write_json

STATUSES = ("radar", "promoted", "dismissed")
FEEDBACK_KINDS = ("interesting", "not_useful", "not_my_topic", "deep_dive")


def radar_id(url: str, title: str) -> str:
    """Stable id for one Radar item, so a Telegram reaction days later
    still addresses the thing it was shown. Derived from the URL where
    there is one — the same item seen through two feeds is one item."""
    basis = (url or title or "").strip().lower()
    return "r" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:15]


def month_key(when: str | None = None) -> str:
    stamp = when or now_iso()
    return stamp[:7]


class Radar:
    """Loaded lazily per month touched, written once at the end."""

    def __init__(self, dry_run: bool = True, directory: Path = RADAR_COLLECTION_DIR):
        self.dry_run = dry_run
        self.dir = directory
        self._months: dict[str, list[dict]] = {}
        self._loaded: set[str] = set()

    # -- storage -----------------------------------------------------

    def _path(self, month: str) -> Path:
        return self.dir / f"{month}.json"

    def _load(self, month: str) -> list[dict]:
        if month not in self._loaded:
            doc = read_json(self._path(month), {"month": month, "items": []})
            self._months[month] = doc.get("items", [])
            self._loaded.add(month)
        return self._months.setdefault(month, [])

    def _all(self) -> list[dict]:
        """Every item across every month, newest first — including
        months this process has only in memory.

        Reading the directory alone was a real bug: an item added and
        then immediately looked up (which is exactly what
        `set_status(..., "promoted")` does after a publish) was invisible
        until save(), so a published post would never have been marked
        promoted on the Radar and would have gone on appearing in the
        digest as "not published".
        """
        months = set(self._months)
        if self.dir.exists():
            months |= {path.stem for path in self.dir.glob("*.json")}
        rows: list[dict] = []
        for month in sorted(months):
            rows.extend(self._load(month))
        return sorted(rows, key=lambda r: r.get("seenAt", ""), reverse=True)

    # -- writing -----------------------------------------------------

    def add(
        self,
        *,
        url: str,
        title: str,
        source: str,
        section: str,
        topics: list[str],
        quality: float,
        relevance: float,
        why: str,
        seen_at: str | None = None,
    ) -> dict:
        """`seen_at` defaults to now, and callers should leave it that
        way: it is when the pipeline SAW the item, not when the source
        published it. Passing the article's own date was tried and
        scattered one sweep across twenty-four monthly files.

        Idempotent on (url, title): seeing the same item on the next
        hourly run refreshes its scores rather than adding a second row.
        Without that, a feed that carries an item for a week would put
        seven identical lines in the digest."""
        stamp = seen_at or now_iso()
        month = month_key(stamp)
        items = self._load(month)
        item_id = radar_id(url, title)

        for existing in items:
            if existing["id"] == item_id:
                existing.update(
                    qualityScore=round(float(quality), 1),
                    relevanceScore=round(float(relevance), 1),
                    whyRelevant=why[:200],
                )
                return existing

        record = {
            "id": item_id,
            "url": url,
            "title": title,
            "source": source,
            "section": section,
            "topics": topics[:3],
            "qualityScore": round(float(quality), 1),
            "relevanceScore": round(float(relevance), 1),
            "whyRelevant": why[:200],
            "seenAt": stamp,
            "status": "radar",
        }
        items.append(record)
        return record

    def find(self, item_id: str) -> dict | None:
        for item in self._all():
            if item.get("id") == item_id:
                return item
        return None

    def set_status(
        self, item_id: str, status: str, *, promoted_to: str | None = None
    ) -> dict | None:
        """The three transitions §6.1 allows:
          radar -> promoted   written up as a post (`promotedTo` = slug)
          radar -> dismissed  retracted or explicitly not wanted
          anything -> radar   is not a transition; items start there.
        """
        if status not in STATUSES:
            raise ValueError(f"unknown radar status {status!r}")
        item = self.find(item_id)
        if item is None:
            return None
        item["status"] = status
        if promoted_to:
            item["promotedTo"] = promoted_to
        return item

    def set_feedback(self, item_id: str, feedback: str) -> dict | None:
        if feedback not in FEEDBACK_KINDS:
            raise ValueError(f"unknown feedback kind {feedback!r}")
        item = self.find(item_id)
        if item is None:
            return None
        item["feedback"] = feedback
        return item

    def demote_post(
        self, *, url: str, title: str, source: str, section: str, topics: list[str],
        quality: float, relevance: float, why: str, slug: str,
    ) -> dict:
        """§11.2 retract: a published post comes back to the Radar with
        status "dismissed". It is not deleted — the whole point of a
        retraction is that the record of it survives."""
        item = self.add(
            url=url, title=title, source=source, section=section, topics=topics,
            quality=quality, relevance=relevance, why=why,
        )
        item["status"] = "dismissed"
        item["promotedTo"] = slug
        return item

    # -- reading -----------------------------------------------------

    def top(self, limit: int = 5, *, status: str = "radar") -> list[dict]:
        """Highest-relevance items still sitting on the Radar — the
        "Top of Radar (not published)" block in the daily digest."""
        rows = [r for r in self._all() if r.get("status") == status]
        return sorted(rows, key=lambda r: r.get("relevanceScore", 0), reverse=True)[:limit]

    def since(self, hours: int = 24) -> list[dict]:
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        out = []
        for row in self._all():
            try:
                seen = datetime.fromisoformat(row["seenAt"])
            except (KeyError, ValueError):
                continue
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if seen.timestamp() >= cutoff:
                out.append(row)
        return out

    def count(self, *, status: str | None = None) -> int:
        rows = self._all()
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return len(rows)

    # -- persistence -------------------------------------------------

    def save(self) -> None:
        """The Radar IS written in a dry run, and deliberately so: it
        contains no publication, it is the observability output Phase 3
        is graded on, and a dry run that filled nothing would prove
        nothing about the scoring. What a dry run must never touch is
        the ledger and the post files."""
        for month, items in self._months.items():
            if not items:
                continue
            write_json(self._path(month), {"month": month, "items": items})
