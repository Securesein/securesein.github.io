"""
Regression test for the incident fixed 2026-09-21: publish_ranked()
(core/pipeline.py) only stopped once per_run_cap posts had actually
PUBLISHED. A candidate that failed verification (G1/G3) still cost a
full draft call and the loop just moved to the next ranked candidate —
nothing bounded how many it could try. A research.yml run with a 96%
quality-gate pass rate and a 74% verification-rejection rate burned 35
draft calls chasing 2 successful publishes.

This locks in max_draft_attempts(): even when every single candidate
fails verification, the loop must stop drafting after the configured
cap rather than working through the whole ranked list.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import pipeline  # noqa: E402
from core.ledger import Verdict  # noqa: E402


@dataclass
class _FakeItem:
    url: str
    title: str


@dataclass
class _FakeCandidate:
    item: _FakeItem
    section: str = "research"
    topics: list = field(default_factory=lambda: ["llms"])
    quality: object = None
    relevance: object = None
    why: str = ""
    _score: float = 50.0

    @property
    def id(self) -> str:
        return self.item.url

    @property
    def score(self) -> float:
        return self._score


class _FakeQueue:
    def __init__(self):
        self.put_rows = []
        self.dropped = []

    def put(self, channel, row, score):
        self.put_rows.append(row)

    def drop(self, row):
        self.dropped.append(row)


class _FakeLedger:
    """Never refuses on budget grounds — this test is isolating the
    ATTEMPT cap specifically, not the existing per_run_cap behaviour,
    which already has its own coverage via can_publish's own tests."""

    def __init__(self, max_attempts: int):
        self._max_attempts = max_attempts

    def can_publish(self, section, published_this_run=0):
        return Verdict(True, "", "")

    def refuse(self, *args, **kwargs):
        raise AssertionError("budget refusal path should not fire in this test")

    def max_draft_attempts(self) -> int:
        return self._max_attempts


class _FakeCtx:
    def __init__(self, max_attempts: int):
        self.ledger = _FakeLedger(max_attempts)
        self.queue = _FakeQueue()


def _outcome_with(n: int) -> pipeline.Outcome:
    candidates = [
        _FakeCandidate(item=_FakeItem(url=f"https://example.com/{i}", title=f"Item {i}"),
                       _score=100.0 - i)
        for i in range(n)
    ]
    return pipeline.Outcome(ranked=candidates)


def test_stops_drafting_after_max_attempts_even_if_every_draft_fails(monkeypatch):
    calls = []

    def fake_publish(ctx, candidate, *, channel, section_rules=""):
        calls.append(candidate.id)
        return None  # every draft fails verification, same as the incident

    monkeypatch.setattr(pipeline, "publish", fake_publish)

    ctx = _FakeCtx(max_attempts=3)
    outcome = _outcome_with(20)  # far more candidates than the cap

    published = pipeline.publish_ranked(ctx, outcome, channel="research", section="research")

    assert published == 0
    assert len(calls) == 3, "must not draft past the attempt cap"
    # The 3 attempted candidates failed verification and were rejected
    # inside publish() itself (not this test's concern — publish is
    # mocked out); only the 17 never given a chance land in the queue.
    assert len(ctx.queue.put_rows) == 17


def test_stops_counting_attempts_once_a_success_satisfies_the_run(monkeypatch):
    """A normal run (most drafts succeed) must not be throttled by the
    attempt cap — this is purely a runaway-cost circuit breaker."""
    def fake_publish(ctx, candidate, *, channel, section_rules=""):
        return "some-slug"

    monkeypatch.setattr(pipeline, "publish", fake_publish)

    ctx = _FakeCtx(max_attempts=8)
    outcome = _outcome_with(5)

    published = pipeline.publish_ranked(ctx, outcome, channel="research", section="research")

    assert published == 5
    assert ctx.queue.put_rows == []
