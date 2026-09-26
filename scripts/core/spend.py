"""
The spend circuit breaker.

Every budget that existed before this module counted POSTS: per run,
per day, per rolling week, plus a cap on draft attempts added after the
2026-09-21 incident. None of them counted money, and none of them
counted the calls that happen before a draft is ever attempted.

That mattered, because the expensive part of a run is not the drafting.
A run classifies and quality-gates EVERY surviving candidate, and scores
a `why_relevant` for every one that passes the gate — three calls per
item, before `max_draft_attempts_per_run` has anything to bite on. The
21 September run made 438 model calls; roughly 340 of those were in that
per-candidate stage, which no cap touched. `limit` in feeds.fetch() is
30 items PER SOURCE, so that stage scales linearly with the number of
feeds configured — and on the first run after new sources are added,
nothing has been seen before, so deduplication removes none of it.

So this module counts two things and stops the run on either:

  - model calls, which is price-independent and therefore still correct
    if the price table below is stale or wrong;
  - estimated spend in dollars, which is what actually matters.

Both are enforced inside LLM itself rather than in the pipeline, because
LLM is the one place every paid call has to pass through. A check in
pipeline.py would be bypassed by the next channel or adapter someone
adds; a check here cannot be.

Failure is deliberately biased towards stopping:

  - a model with no price entry is charged at the most expensive known
    rate, not skipped;
  - a response that reports no token usage is charged a pessimistic
    fixed estimate, not zero;
  - if the spend file is unreadable, the run refuses to start rather
    than assuming a clean slate.

Crossing a ceiling raises BudgetExceeded, which aborts the run before it
commits anything. A run that dies this way publishes nothing, which is
the intended outcome: an incident to look at, not output to keep.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .constants import CONFIG_DIR, STATE_DIR
from .state import now_iso, read_json, write_json

BUDGETS_FILE = CONFIG_DIR / "budgets.json"
SPEND_FILE = STATE_DIR / "spend.json"


class BudgetExceeded(RuntimeError):
    """A ceiling was crossed. Raised from inside LLM so it interrupts
    whatever the pipeline was doing rather than being swallowed by the
    per-call `except` that treats a failed call as a skipped item."""


@dataclass
class SpendGuard:
    """Counts what this run has spent and refuses the call that would
    cross a ceiling. One instance per run, owned by LLM."""

    max_calls_per_run: int
    max_run_usd: float
    max_day_usd: float
    max_7d_usd: float
    max_30d_usd: float
    prices: dict[str, dict[str, float]]
    fallback_price: dict[str, float]
    unknown_usage_tokens: dict[str, int]
    prior_day_usd: float = 0.0
    prior_7d_usd: float = 0.0
    prior_30d_usd: float = 0.0

    calls: int = 0
    run_usd: float = 0.0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    # -- pricing ----------------------------------------------------

    def price_for(self, model: str) -> dict[str, float]:
        """Unknown models are charged at the most expensive rate in the
        table. A model nobody priced is the one most likely to be new,
        and guessing cheap is how a price table turns into a hole."""
        if model in self.prices:
            return self.prices[model]
        if not self.prices:
            return self.fallback_price
        return max(
            self.prices.values(),
            key=lambda p: p.get("output_per_1m", 0.0),
        )

    def cost_of(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        price = self.price_for(model)
        return (
            prompt_tokens / 1_000_000 * price.get("input_per_1m", 0.0)
            + completion_tokens / 1_000_000 * price.get("output_per_1m", 0.0)
        )

    # -- the two hooks LLM calls ------------------------------------

    def reserve_for(self, model: str) -> float:
        """What the call about to be made might cost. Checking only what
        has ALREADY been spent means the ceiling is crossed before
        anything notices — with a dollar of headroom left, a call that
        costs two is allowed and the ceiling is simply exceeded. The
        ceilings are supposed to not be crossed, so the next call has to
        fit under them before it is made."""
        return self.cost_of(
            model,
            self.unknown_usage_tokens.get("prompt", 4000),
            self.unknown_usage_tokens.get("completion", 1500),
        )

    def check_before_call(self, model: str, label: str = "") -> None:
        """Raises rather than returning a verdict: this has to interrupt
        the caller, and every call site already treats a returned None
        as 'skip this item and carry on', which is exactly the behaviour
        that must not happen here."""
        where = f" ({label})" if label else ""
        if self.calls >= self.max_calls_per_run:
            raise BudgetExceeded(
                f"model-call ceiling reached: {self.calls} calls this run "
                f"(max {self.max_calls_per_run}){where}. "
                f"Estimated spend so far ${self.run_usd:.2f}."
            )

        reserve = self.reserve_for(model)
        if self.run_usd + reserve >= self.max_run_usd:
            raise BudgetExceeded(
                f"per-run spend ceiling would be crossed by the next call: "
                f"${self.run_usd:.2f} spent + ~${reserve:.2f} reserved "
                f"(max ${self.max_run_usd:.2f}) after {self.calls} calls{where}."
            )
        day = self.prior_day_usd + self.run_usd
        if day + reserve >= self.max_day_usd:
            raise BudgetExceeded(
                f"daily spend ceiling would be crossed by the next call: "
                f"${day:.2f} today + ~${reserve:.2f} reserved "
                f"(max ${self.max_day_usd:.2f}){where}."
            )
        week = self.prior_7d_usd + self.run_usd
        if week + reserve >= self.max_7d_usd:
            raise BudgetExceeded(
                f"7-day spend ceiling would be crossed by the next call: "
                f"${week:.2f} this week + ~${reserve:.2f} reserved "
                f"(max ${self.max_7d_usd:.2f}){where}."
            )
        month = self.prior_30d_usd + self.run_usd
        if month + reserve >= self.max_30d_usd:
            raise BudgetExceeded(
                f"30-day spend ceiling would be crossed by the next call: "
                f"${month:.2f} over the rolling month + ~${reserve:.2f} reserved "
                f"(max ${self.max_30d_usd:.2f}){where}."
            )

    def record(self, model: str, usage: object | None) -> float:
        """Charge one completed call. `usage` is the SDK's usage object;
        when it is absent or unreadable the call is charged a pessimistic
        fixed estimate, because the alternative — charging nothing — makes
        a provider that stops reporting usage look free."""
        self.calls += 1
        prompt = completion = None
        if usage is not None:
            prompt = getattr(usage, "prompt_tokens", None)
            completion = getattr(usage, "completion_tokens", None)
        estimated = prompt is None or completion is None
        if estimated:
            prompt = self.unknown_usage_tokens.get("prompt", 4000)
            completion = self.unknown_usage_tokens.get("completion", 1500)

        cost = self.cost_of(model, int(prompt), int(completion))
        self.run_usd += cost

        row = self.by_model.setdefault(
            model, {"calls": 0, "usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0,
                    "estimated_calls": 0}
        )
        row["calls"] += 1
        row["usd"] += cost
        row["prompt_tokens"] += int(prompt)
        row["completion_tokens"] += int(completion)
        if estimated:
            row["estimated_calls"] += 1
        return cost

    # -- reporting --------------------------------------------------

    def summary(self) -> str:
        parts = [f"{self.calls} model call(s), ~${self.run_usd:.3f} this run"]
        if self.max_run_usd:
            parts.append(f"{self.run_usd / self.max_run_usd * 100:.0f}% of the run ceiling")
        day = self.prior_day_usd + self.run_usd
        parts.append(f"~${day:.2f} today of ${self.max_day_usd:.2f}")
        week = self.prior_7d_usd + self.run_usd
        parts.append(f"~${week:.2f} this week of ${self.max_7d_usd:.2f}")
        month = self.prior_30d_usd + self.run_usd
        parts.append(f"~${month:.2f} this month of ${self.max_30d_usd:.2f}")
        return "; ".join(parts)


# -- persistence ----------------------------------------------------


def _entries() -> list[dict]:
    data = read_json(SPEND_FILE, {"entries": []})
    entries = data.get("entries")
    if not isinstance(entries, list):
        # Refuse rather than reset: an unreadable spend file with the
        # ceilings enforced against it is indistinguishable from a clean
        # slate, and starting over is the failure mode that lets the
        # same money be spent twice.
        raise BudgetExceeded(
            f"{SPEND_FILE} is unreadable — refusing to start a run with no "
            f"idea what has already been spent. Inspect and repair it."
        )
    return entries


def _window_total(entries: list[dict], *, days: float, now: datetime | None = None) -> float:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    total = 0.0
    for entry in entries:
        stamp = entry.get("at")
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            total += float(entry.get("usd", 0.0))
    return total


def load_config() -> dict:
    config = json.loads(BUDGETS_FILE.read_text(encoding="utf-8"))
    return config.get("spend", {})


def new_guard(*, now: datetime | None = None) -> SpendGuard:
    """Build the guard for a run, with the day and week windows already
    loaded so the first call of a run is checked against them too."""
    cfg = load_config()
    entries = _entries()
    return SpendGuard(
        max_calls_per_run=int(cfg.get("max_model_calls_per_run", 150)),
        max_run_usd=float(cfg.get("max_spend_per_run_usd", 1.50)),
        max_day_usd=float(cfg.get("max_spend_per_day_usd", 4.00)),
        max_7d_usd=float(cfg.get("max_spend_7d_usd", 3.00)),
        max_30d_usd=float(cfg.get("max_spend_30d_usd", 10.00)),
        prices=cfg.get("prices", {}),
        fallback_price=cfg.get("fallback_price", {"input_per_1m": 10.0, "output_per_1m": 30.0}),
        unknown_usage_tokens=cfg.get("unknown_usage_tokens", {"prompt": 4000, "completion": 1500}),
        prior_day_usd=_window_total(entries, days=1, now=now),
        prior_7d_usd=_window_total(entries, days=7, now=now),
        prior_30d_usd=_window_total(entries, days=30, now=now),
    )


def preflight(guard: SpendGuard) -> None:
    """Refuse to start at all when a window is already exhausted, so an
    exhausted budget costs zero calls rather than one."""
    if guard.prior_day_usd >= guard.max_day_usd:
        raise BudgetExceeded(
            f"daily spend ceiling already reached before this run: "
            f"${guard.prior_day_usd:.2f} of ${guard.max_day_usd:.2f}. Not starting."
        )
    if guard.prior_7d_usd >= guard.max_7d_usd:
        raise BudgetExceeded(
            f"7-day spend ceiling already reached before this run: "
            f"${guard.prior_7d_usd:.2f} of ${guard.max_7d_usd:.2f}. Not starting."
        )
    if guard.prior_30d_usd >= guard.max_30d_usd:
        raise BudgetExceeded(
            f"30-day spend ceiling already reached before this run: "
            f"${guard.prior_30d_usd:.2f} of ${guard.max_30d_usd:.2f}. Not starting."
        )


def record_run(guard: SpendGuard, *, channel: str, aborted: bool = False) -> None:
    """Append this run's spend. Called on the way out whether or not the
    run finished, because an aborted run still spent what it spent and
    the next run has to see it."""
    if guard.calls == 0:
        return
    data = read_json(SPEND_FILE, {"entries": []})
    data.setdefault("entries", []).append(
        {
            "at": now_iso(),
            "channel": channel,
            "calls": guard.calls,
            "usd": round(guard.run_usd, 6),
            "aborted": aborted,
            "by_model": {
                m: {**row, "usd": round(row["usd"], 6)} for m, row in guard.by_model.items()
            },
        }
    )
    # A rolling window never needs more than a few weeks of history.
    data["entries"] = data["entries"][-500:]
    write_json(SPEND_FILE, data)
