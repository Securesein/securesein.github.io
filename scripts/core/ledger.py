"""
The publication ledger and its rolling-window budgets (brief §9).

Every auto-published post across every channel is recorded here, and
every channel asks this module for permission before it publishes. That
is the whole design: the channels do not know about each other, and the
only thing that stops four channels from independently deciding today is
a good day to publish is one shared counter.

Budgets are keyed by SECTION, not by channel. Two channels can publish
into the same section (a benchmark roundup and a research piece can both
cite measurements), and a per-channel counter would let them overshoot
the site's actual output target while each stayed inside its own budget.

**Rolling 7 days, not a calendar week.** A calendar week resets on
Monday, which permits a full week's output on Sunday night and another
full week's output on Monday morning — a hundred posts inside 48 hours,
each run perfectly within its "weekly" budget.

**Unused budget does not roll over.** A quiet week is a quiet week, and
§16 is explicit that this is a correct outcome rather than a failure to
hit target. Nothing here carries a remainder forward.

**The hard cap should never bind.** If it does, that is an incident: it
means a threshold somewhere is set too low and a channel is producing
volume it was never meant to. Hitting it is reported as such rather than
logged as a routine truncation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .constants import CONFIG_DIR, LEDGER_FILE, QUEUE_FILE
from .state import now_iso, read_json, reject, write_json

BUDGETS_FILE = CONFIG_DIR / "budgets.json"
WINDOW_DAYS = 7


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str
    detail: str

    def __bool__(self) -> bool:  # so `if ledger.can_publish(...)` reads
        return self.allowed


class Ledger:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.config = json.loads(BUDGETS_FILE.read_text(encoding="utf-8"))
        self.entries: list[dict] = read_json(LEDGER_FILE, {"entries": []})["entries"]
        # Publications this process has decided on, counted against the
        # budget even in a dry run so that "what would this run have
        # done" is answerable without actually doing it.
        self.pending: list[dict] = []

    # -- window arithmetic -------------------------------------------

    def _rows_since(self, cutoff: datetime, section: str | None = None) -> list[dict]:
        rows = []
        for entry in [*self.entries, *self.pending]:
            if section and entry.get("section") != section:
                continue
            try:
                published = datetime.fromisoformat(entry["publishedAt"])
            except (KeyError, ValueError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published >= cutoff:
                rows.append(entry)
        return rows

    def used(self, section: str | None = None) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
        return len(self._rows_since(cutoff, section))

    def used_today(self) -> int:
        """Rolling 24 hours, for the same reason the week is rolling."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        return len(self._rows_since(cutoff))

    def target(self, section: str) -> int:
        return int(self.config["targets_7d"].get(section, 0))

    def per_run_cap(self) -> int:
        return int(self.config["per_run_cap"])

    def max_draft_attempts(self) -> int:
        """Bounds cost per run independently of per_run_cap: that cap
        stops the loop once N posts have PUBLISHED, but a candidate that
        fails verification (G1/G3) still cost a full draft call and
        previously didn't count against anything — see budgets.json's
        own comment on the incident this fixes."""
        return int(self.config.get("max_draft_attempts_per_run", 8))

    def per_day_cap(self) -> int:
        return int(self.config["per_day_cap"])

    def hard_cap(self) -> int:
        return int(self.config["hard_cap_7d"])

    def remaining(self, section: str) -> int:
        by_section = self.target(section) - self.used(section)
        by_global = self.hard_cap() - self.used()
        by_day = self.per_day_cap() - self.used_today()
        return max(0, min(by_section, by_global, by_day))

    # -- the actual gate ---------------------------------------------

    def can_publish(self, section: str, published_this_run: int = 0) -> Verdict:
        """Checked in escalating order of how alarming a refusal is, so
        the reason written to rejected.jsonl is the most informative one
        rather than whichever check happened to run first."""
        if self.used() >= self.hard_cap():
            return Verdict(
                False,
                "global_cap_reached",
                f"INCIDENT: the global circuit breaker of {self.hard_cap()} posts "
                f"per rolling 7 days has been reached. This should never happen "
                f"in normal operation — a threshold somewhere is set too low.",
            )
        if published_this_run >= self.per_run_cap():
            return Verdict(
                False,
                "per_run_cap",
                f"{section}: already published {published_this_run} this run "
                f"(per-run cap {self.per_run_cap()})",
            )
        if self.used_today() >= self.per_day_cap():
            return Verdict(
                False,
                "per_day_cap",
                f"{self.used_today()}/{self.per_day_cap()} posts in the last 24 "
                f"hours across all sections — the day is full.",
            )
        if self.used(section) >= self.target(section):
            return Verdict(
                False,
                "section_budget_exhausted",
                f"{section}: {self.used(section)}/{self.target(section)} used in "
                f"the rolling 7-day window — top candidate stays queued.",
            )
        return Verdict(
            True,
            "ok",
            f"{section}: {self.used(section)}/{self.target(section)} used, "
            f"{self.used()}/{self.hard_cap()} globally, "
            f"{self.used_today()}/{self.per_day_cap()} today.",
        )

    def refuse(
        self, channel: str, verdict: Verdict, *, title: str, score: float | None
    ) -> None:
        """Log a budget refusal. Deliberately a different `reason` class
        from a quality drop — see core/state.py. §9: "budget drops and
        quality drops are different events with different reasons"."""
        print(f"    Not publishing — {verdict.detail}")
        reject(
            channel,
            verdict.reason,
            title=title,
            score=score,
            detail=verdict.detail,
            dry_run=self.dry_run,
        )

    # -- recording ---------------------------------------------------

    def record(
        self,
        slug: str,
        channel: str,
        section: str,
        *,
        quality: float | None = None,
        relevance: float | None = None,
    ) -> None:
        """Records what a publish *did*, or in a dry run what it *would*
        have done. §9 fixes the shape: slug, section, publishedAt,
        qualityScore, relevanceScore. The dry-run flag rides along on the
        entry so a later real run can tell the two apart, and dry-run
        entries are kept out of the persisted ledger entirely."""
        entry = {
            "slug": slug,
            "section": section,
            "channel": channel,
            "publishedAt": now_iso(),
            "qualityScore": quality,
            "relevanceScore": relevance,
        }
        if self.dry_run:
            entry["dryRun"] = True
        self.pending.append(entry)

    def save(self) -> None:
        """A dry run must leave no trace in the committed ledger — it
        may read it, count against it in memory, and report on it, but
        it must never make the next real run think it has less budget
        than it has."""
        if self.dry_run:
            print(
                f"    [dry-run] would have recorded {len(self.pending)} "
                f"publication(s) in the ledger; leaving it untouched."
            )
            return
        if not self.pending:
            return
        self.entries.extend(self.pending)
        # Keep a generous tail rather than only the window: the weekly
        # report wants history, and the file stays tiny either way.
        write_json(LEDGER_FILE, {"entries": self.entries[-2000:]})
        self.pending.clear()

    def summary(self) -> dict:
        return {
            "global": {"used": self.used(), "cap": self.hard_cap()},
            "today": {"used": self.used_today(), "cap": self.per_day_cap()},
            "sections": {
                section: {
                    "used": self.used(section),
                    "target": self.target(section),
                }
                for section in self.config["targets_7d"]
            },
        }


# --- the queue: scored candidates that budget could not fit ---------


class Queue:
    """Candidates that passed the quality gate but not the budget. They
    keep their score and wait; a candidate that waits longer than
    `queue_ttl_days` is stale and falls back to the Radar rather than
    being published late (brief §9)."""

    def __init__(self, ledger: Ledger):
        self.ttl_days = int(ledger.config.get("queue_ttl_days", 7))
        self.items: list[dict] = read_json(QUEUE_FILE, {"items": []})["items"]
        self.dry_run = ledger.dry_run

    def prune(self) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)
        kept, expired = [], []
        for item in self.items:
            try:
                queued = datetime.fromisoformat(item["queuedAt"])
            except (KeyError, ValueError):
                expired.append(item)
                continue
            if queued.tzinfo is None:
                queued = queued.replace(tzinfo=timezone.utc)
            (kept if queued >= cutoff else expired).append(item)
        self.items = kept
        return expired

    def put(self, channel: str, candidate: dict, score: float) -> None:
        key = candidate.get("url") or candidate.get("title")
        for item in self.items:
            if (item.get("url") or item.get("title")) == key:
                item["score"] = score
                return
        self.items.append(
            {
                "channel": channel,
                "queuedAt": now_iso(),
                "score": score,
                **candidate,
            }
        )

    def top(self, channel: str, limit: int = 3) -> list[dict]:
        rows = [i for i in self.items if i.get("channel") == channel]
        return sorted(rows, key=lambda i: i.get("score", 0), reverse=True)[:limit]

    def drop(self, candidate: dict) -> None:
        key = candidate.get("url") or candidate.get("title")
        self.items = [
            i for i in self.items if (i.get("url") or i.get("title")) != key
        ]

    def save(self) -> None:
        # The queue is written even in a dry run: it is the observable
        # output Phase 3 is graded on, and it contains no publication.
        write_json(QUEUE_FILE, {"items": self.items})
