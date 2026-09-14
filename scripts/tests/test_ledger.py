"""
The publication ledger: rolling window, per-SECTION targets, the global
circuit breaker, the per-day cap, and the three different classes of
drop (quality, budget, exclusion).

Budgets moved from per-channel to per-section in this build: two
channels can publish into one section, and a per-channel counter would
let them overshoot the site's actual output while each stayed inside
its own budget.

These are the rules that decide whether anything publishes at all, so
they are tested against a synthetic ledger rather than the real one —
the real file's contents change every run, and a test that depends on
them tells you about last week rather than about the code.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import ledger as ledger_module  # noqa: E402
from core.ledger import Ledger, Queue  # noqa: E402


def _entries(channel: str, count: int, days_ago: float) -> list[dict]:
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return [
        {"slug": f"{channel}-{i}", "section": channel, "channel": channel, "publishedAt": when, "score": 7}
        for i in range(count)
    ]


class _FakeLedger(Ledger):
    """A Ledger over a hand-built entry list, with saving disabled."""

    def __init__(self, entries: list[dict], dry_run: bool = True):
        self.dry_run = dry_run
        self.config = json.loads(
            (REPO_ROOT / "config" / "budgets.json").read_text(encoding="utf-8")
        )
        self.entries = entries
        self.pending = []


def test_window_is_rolling_not_calendar():
    """The failure a calendar week permits: a full week's output on
    Sunday night and another on Monday morning. Eight releases six days
    ago must still count against today's budget."""
    ledger = _FakeLedger(_entries("release", 8, days_ago=6))
    assert ledger.used("release") == 8
    assert not ledger.can_publish("release").allowed

    # The same eight, eight days ago, have aged out.
    ledger = _FakeLedger(_entries("release", 8, days_ago=8))
    assert ledger.used("release") == 0
    assert ledger.can_publish("release").allowed


def test_section_target_stops_that_section_only():
    ledger = _FakeLedger(_entries("release", 8, days_ago=1))
    releases = ledger.can_publish("release")
    assert not releases.allowed
    assert releases.reason == "section_budget_exhausted"
    # Research is untouched by Model Updates running out.
    assert ledger.can_publish("research").allowed


def test_global_cap_is_an_incident_not_a_truncation():
    """Fifty posts inside the window stops everything, and says so in
    the language of an incident — a threshold is set too low somewhere,
    which is a different problem from a channel doing its job."""
    entries = (
        _entries("research", 20, 1) + _entries("release", 8, 1) + _entries("benchmark", 2, 1)
    )
    entries += _entries("research", 20, 2)  # over target, and over the cap in total
    ledger = _FakeLedger(entries)
    assert ledger.used() >= ledger.hard_cap()
    verdict = ledger.can_publish("research")
    assert not verdict.allowed
    assert verdict.reason == "global_cap_reached"
    assert "INCIDENT" in verdict.detail


def test_per_run_cap():
    ledger = _FakeLedger([])
    cap = ledger.per_run_cap()
    assert ledger.can_publish("release", published_this_run=cap - 1).allowed
    verdict = ledger.can_publish("release", published_this_run=cap)
    assert not verdict.allowed
    assert verdict.reason == "per_run_cap"


def test_per_day_cap_is_rolling_too():
    """§9 sets a per-day cap as well as a weekly one, and it is rolling
    for the same reason the week is: a midnight reset would permit two
    days' output inside an hour."""
    ledger = _FakeLedger(_entries("research", 5, days_ago=0.5))
    verdict = ledger.can_publish("research")
    assert not verdict.allowed
    assert verdict.reason == "per_day_cap"
    # The same five, two days ago, no longer bind the day.
    ledger = _FakeLedger(_entries("research", 5, days_ago=2))
    assert ledger.can_publish("research").allowed


def test_unused_budget_does_not_roll_over():
    """§9: "a quiet week is a quiet week". A section that published
    nothing last week gets this week's target, not two weeks' worth."""
    ledger = _FakeLedger(_entries("research", 6, days_ago=20))
    assert ledger.used("research") == 0
    # `remaining` is the tightest of the three limits, so a quiet week
    # restores the full weekly target — clipped only by what a single
    # day is allowed to carry, which is a different rule.
    assert ledger.remaining("research") == min(
        ledger.target("research"), ledger.per_day_cap()
    )
    assert ledger.remaining("research") > 0


def test_budget_and_quality_rejections_are_different_events():
    """Brief §9: dropping for budget and dropping for quality are
    different events and must be logged with different reasons, and an
    excluded item is neither. The `class` field is what makes all three
    separable in the weekly report."""
    from core.state import BUDGET_REASONS, EXCLUSION_REASONS, QUALITY_REASONS

    assert BUDGET_REASONS & QUALITY_REASONS == set()
    assert EXCLUSION_REASONS & QUALITY_REASONS == set()
    assert EXCLUSION_REASONS & BUDGET_REASONS == set()
    ledger = _FakeLedger(_entries("release", 8, 1))
    assert ledger.can_publish("release").reason in BUDGET_REASONS


def test_pending_publications_count_against_the_budget_in_a_dry_run():
    """A dry run has to answer "what would this run have done", which
    means its own decisions have to consume budget in memory even
    though nothing is written."""
    # Five days ago, so the rolling DAY cap is not what is being
    # measured here — the weekly section target is.
    ledger = _FakeLedger(_entries("release", 5, 5), dry_run=True)
    assert ledger.can_publish("release").allowed
    ledger.record("a-release", "releases", "release", quality=70, relevance=60)
    assert ledger.used("release") == 6
    assert not ledger.can_publish("release").allowed


def test_dry_run_leaves_the_real_ledger_file_untouched(tmp=None):
    """The one thing a dry run must never do."""
    real = ledger_module.LEDGER_FILE
    before = real.read_bytes() if real.exists() else None
    ledger = Ledger(dry_run=True)
    ledger.record("would-have-published", "releases", "release",
                  quality=70, relevance=60)
    ledger.save()
    after = real.read_bytes() if real.exists() else None
    assert before == after


def test_queue_expires_stale_candidates():
    queue = Queue(_FakeLedger([]))
    queue.items = [
        {"channel": "releases", "title": "fresh", "url": "u1",
         "queuedAt": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        {"channel": "releases", "title": "stale", "url": "u2",
         "queuedAt": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()},
    ]
    expired = queue.prune()
    assert [i["title"] for i in expired] == ["stale"]
    assert [i["title"] for i in queue.items] == ["fresh"]
