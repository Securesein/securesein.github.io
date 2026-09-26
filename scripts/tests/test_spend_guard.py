"""
The spend circuit breaker has to actually stop a run, so these tests
are written against the behaviour that matters rather than the shape of
the code: does the next call get refused, does an exhausted window stop
the run before it costs anything, and are the failure modes biased
towards stopping rather than carrying on.

The two that matter most are the last two. A guard that charges zero
for an unpriced model, or zero for a response that reports no usage,
looks like it is working right up until the moment it isn't — and both
are exactly what happens when a provider changes something.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import spend  # noqa: E402
from core.spend import BudgetExceeded, SpendGuard  # noqa: E402


def make_guard(**over):
    base = dict(
        max_calls_per_run=10,
        max_run_usd=1.00,
        max_day_usd=4.00,
        max_7d_usd=15.00,
        max_30d_usd=50.00,
        prices={
            "cheap": {"input_per_1m": 0.15, "output_per_1m": 0.60},
            "dear": {"input_per_1m": 2.50, "output_per_1m": 10.00},
        },
        fallback_price={"input_per_1m": 10.0, "output_per_1m": 30.0},
        unknown_usage_tokens={"prompt": 4000, "completion": 1500},
    )
    base.update(over)
    return SpendGuard(**base)


class FakeUsage:
    def __init__(self, prompt, completion):
        self.prompt_tokens = prompt
        self.completion_tokens = completion


def test_call_ceiling_refuses_the_next_call():
    """The price-independent backstop: still correct when the price
    table is stale, which is the state it will spend most of its life
    in."""
    guard = make_guard(max_calls_per_run=3)
    for _ in range(3):
        guard.check_before_call("cheap")
        guard.record("cheap", FakeUsage(100, 50))

    try:
        guard.check_before_call("cheap")
    except BudgetExceeded as exc:
        assert "model-call ceiling" in str(exc)
    else:
        raise AssertionError("the fourth call should have been refused")


def test_run_spend_ceiling_refuses_the_next_call():
    guard = make_guard(max_run_usd=0.10)
    # one dear call at 1M in / 1M out is far past a ten-cent ceiling
    guard.check_before_call("dear")
    guard.record("dear", FakeUsage(1_000_000, 1_000_000))
    assert guard.run_usd > 0.10

    try:
        guard.check_before_call("dear")
    except BudgetExceeded as exc:
        assert "per-run spend ceiling" in str(exc)
    else:
        raise AssertionError("the run ceiling should have refused the next call")


def test_day_and_week_windows_include_what_earlier_runs_spent():
    """Per-run ceilings alone would let N runs spend N times the cap, so
    the windows carry prior spend into this run's very first check.
    A dear call needs ~$0.025 of headroom and there is only $0.01."""
    guard = make_guard(max_day_usd=1.00, prior_day_usd=0.99)
    try:
        guard.check_before_call("dear")
    except BudgetExceeded as exc:
        assert "daily spend ceiling" in str(exc)
    else:
        raise AssertionError("prior spend today should have been counted")

    weekly = make_guard(max_7d_usd=5.00, prior_7d_usd=4.99)
    try:
        weekly.check_before_call("dear")
    except BudgetExceeded as exc:
        assert "7-day spend ceiling" in str(exc)
    else:
        raise AssertionError("prior spend this week should have been counted")


def test_headroom_is_judged_per_model_not_blanket():
    """The same $0.01 of headroom that refuses a dear call still admits
    a cheap one, because the reserve is what THAT call would cost. A
    blanket refusal would stop classification runs — the cheap, useful
    part — while a single expensive draft slipped through elsewhere."""
    guard = make_guard(max_day_usd=1.00, prior_day_usd=0.99)
    guard.check_before_call("cheap")  # ~$0.0015, fits — must not raise
    assert guard.reserve_for("dear") > guard.reserve_for("cheap")


def test_unpriced_model_is_charged_at_the_dearest_known_rate():
    """An unpriced model is most likely a new one. Charging it nothing
    is how a price table becomes a hole."""
    guard = make_guard()
    known = guard.cost_of("dear", 1_000_000, 1_000_000)
    unknown = guard.cost_of("some-model-shipped-last-tuesday", 1_000_000, 1_000_000)
    assert unknown == known, "an unknown model must not be cheaper than the dearest known one"
    assert unknown > 0


def test_missing_usage_is_charged_a_pessimistic_estimate():
    """A provider that stops reporting usage must not read as free."""
    guard = make_guard()
    guard.record("dear", None)
    assert guard.run_usd > 0, "a call with no usage reported was charged nothing"
    assert guard.by_model["dear"]["estimated_calls"] == 1


def test_preflight_refuses_before_spending_anything():
    guard = make_guard(max_day_usd=1.00, prior_day_usd=1.00)
    try:
        spend.preflight(guard)
    except BudgetExceeded as exc:
        assert "Not starting" in str(exc)
        assert guard.calls == 0, "preflight must not cost a call"
    else:
        raise AssertionError("an exhausted day should refuse the run outright")


def test_window_total_only_counts_entries_inside_the_window():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    entries = [
        {"at": (now - timedelta(hours=2)).isoformat(), "usd": 1.0},   # today
        {"at": (now - timedelta(days=3)).isoformat(), "usd": 2.0},    # this week
        {"at": (now - timedelta(days=30)).isoformat(), "usd": 99.0},  # long gone
        {"at": "not-a-date", "usd": 5.0},                             # ignored
    ]
    assert spend._window_total(entries, days=1, now=now) == 1.0
    assert spend._window_total(entries, days=7, now=now) == 3.0


def test_unreadable_spend_file_refuses_rather_than_resetting(tmp_path, monkeypatch):
    """Treating a corrupt file as a clean slate would let the same
    budget be spent again, which is the one outcome worse than crashing."""
    bad = tmp_path / "spend.json"
    bad.write_text('{"entries": "not a list"}', encoding="utf-8")
    monkeypatch.setattr(spend, "SPEND_FILE", bad)
    try:
        spend._entries()
    except BudgetExceeded as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("a corrupt spend file must not read as zero spent")


def test_the_ceiling_is_not_swallowed_by_the_catch_all():
    """The property most likely to regress. Every call site reads a
    returned None as "skip this item and carry on", and llm.json wraps
    its call in `except Exception -> return None`. If the ceiling ever
    lands inside that, the run keeps going and keeps spending, which is
    the whole failure this module exists to prevent."""
    from core.llm import LLM

    guard = make_guard(max_calls_per_run=0)
    llm = LLM(mode="live", guard=guard)

    try:
        llm.json("anything", model="cheap", label="gate")
    except BudgetExceeded:
        pass
    else:
        raise AssertionError(
            "llm.json returned instead of raising — the ceiling was swallowed"
        )


def test_offline_runs_need_no_guard_and_spend_nothing():
    from core.llm import LLM

    llm = LLM(mode="offline")
    assert llm.guard is None
    assert llm.spend_usd == 0.0
    assert llm.json("x", model="cheap", offline=lambda: {"ok": True}) == {"ok": True}


def test_the_month_is_the_actual_promise():
    """Day and week ceilings bound a spike; neither bounds a month. At
    ~23.5 runs/day a week under its cap four times over is still a
    month over budget, so the 30-day window is the one that holds the
    number the owner actually asked for."""
    guard = make_guard(max_30d_usd=10.00, prior_30d_usd=9.99)
    try:
        guard.check_before_call("dear")
    except BudgetExceeded as exc:
        assert "30-day spend ceiling" in str(exc)
    else:
        raise AssertionError("a spent month should refuse the next call")


def test_an_exhausted_month_refuses_the_run_outright():
    guard = make_guard(max_30d_usd=10.00, prior_30d_usd=10.00)
    try:
        spend.preflight(guard)
    except BudgetExceeded as exc:
        assert "30-day" in str(exc) and "Not starting" in str(exc)
    else:
        raise AssertionError("an exhausted month should not start a run")


def test_configured_ceilings_actually_add_up_to_the_monthly_promise():
    """A day cap that multiplies out past the month cap is not wrong,
    but it must not be the binding one — otherwise the month is bounded
    by arithmetic nobody checked."""
    cfg = spend.load_config()
    assert cfg["max_spend_30d_usd"] <= 10.0, "the monthly promise moved"
    assert cfg["max_spend_per_run_usd"] < cfg["max_spend_per_day_usd"]
    assert cfg["max_spend_per_day_usd"] < cfg["max_spend_7d_usd"]
    assert cfg["max_spend_7d_usd"] < cfg["max_spend_30d_usd"]
