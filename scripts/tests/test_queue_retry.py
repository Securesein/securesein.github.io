"""
A queued candidate that fails to publish used to stay queued.

Rows left the queue only on success, so a candidate that could not be
drafted sat at the top and was drafted again every run — against the
same source text, so to the same conclusion. The only thing that ever
removed it was the seven-day TTL, which at hourly runs is about 168
attempts. Measured on the live pipeline: one Hugging Face repo,
nvidia/RT-DETR-Hand-Detector-v1, went through 184 of them on gpt-4o
and accounted for most of the channel's entire spend.

Two guards, tested here. The specific one drops a candidate whose
draft came back "insufficient", because that is a verdict about the
source rather than a transient failure. The general one caps attempts
whatever the reason, so no future failure mode can rediscover this.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.ledger import Queue  # noqa: E402


class FakeLedger:
    def __init__(self):
        self.config = {"queue_ttl_days": 7}


def _queue_with(rows):
    q = Queue.__new__(Queue)
    q.ledger = FakeLedger()
    q.items = list(rows)
    return q


def test_attempts_accumulate_across_runs():
    row = {"url": "https://huggingface.co/nvidia/RT-DETR", "title": "RT-DETR",
           "channel": "releases", "score": 5}
    q = _queue_with([row])

    assert q.record_attempt(row) == 1
    assert q.record_attempt(row) == 2
    assert q.record_attempt(row) == 3
    assert q.items[0]["attempts"] == 3, "the count has to live on the queued row"


def test_the_count_survives_a_save_and_reload():
    """Each run is a fresh process reading queue.json, so a counter kept
    only in memory would reset every hour and never reach its cap."""
    row = {"url": "https://example.test/a", "title": "A", "channel": "releases"}
    q = _queue_with([row])
    q.record_attempt(row)
    q.record_attempt(row)

    # what save()/read would round-trip
    import json
    reloaded = _queue_with(json.loads(json.dumps(q.items)))
    assert reloaded.record_attempt(reloaded.items[0]) == 3


def test_a_dropped_row_stops_coming_back():
    row = {"url": "https://example.test/a", "title": "A", "channel": "releases"}
    q = _queue_with([row])
    q.drop(row)
    assert q.top("releases") == [], "a dropped row was still offered"


def test_the_cap_is_far_below_what_the_ttl_allowed():
    """The TTL is not a cost control. At hourly runs seven days is
    around 168 attempts; the point of the cap is to be nowhere near
    that while still tolerating a flaky fetch."""
    from channels.releases import MAX_PUBLISH_ATTEMPTS

    assert MAX_PUBLISH_ATTEMPTS <= 5
    assert MAX_PUBLISH_ATTEMPTS >= 2, "one attempt would drop on a transient failure"
