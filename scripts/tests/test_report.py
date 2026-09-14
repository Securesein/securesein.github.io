"""
The weekly report (brief §11).

Six things have to be in it, and the report is the only way any of them
is visible once a pipeline publishes without review. The test drives it
against synthetic state rather than the real files, so it measures the
report rather than last week.

NOTHING HERE SENDS A TELEGRAM MESSAGE. `report.send` is never called;
the test asserts the report is generated and inspectable, which is
exactly the Phase 6 acceptance criterion.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from channels import report as report_module  # noqa: E402
from test_ledger import _FakeLedger, _entries  # noqa: E402


def _now(days_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _seed(tmp: Path) -> None:
    """Synthetic state files, swapped in for the real ones."""
    (tmp / "rejected.jsonl").write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"at": _now(1), "channel": "releases", "reason": "not_a_release",
                 "class": "quality", "title": "Ollama v0.14.2"},
                {"at": _now(1), "channel": "releases", "reason": "not_a_release",
                 "class": "quality", "title": "SDK 1.2.3"},
                {"at": _now(2), "channel": "releases",
                 "reason": "gate_g1_ungrounded_number", "class": "quality",
                 "title": "A draft that rounded a score"},
                {"at": _now(2), "channel": "releases",
                 "reason": "section_budget_exhausted", "class": "budget",
                 "title": "A perfectly good release"},
                {"at": _now(30), "channel": "news", "reason": "duplicate_url",
                 "class": "quality", "title": "Outside the window"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp / "adapter_failures.jsonl").write_text(
        json.dumps({"at": _now(1), "adapter": "lmarena",
                    "error": "RuntimeError: pickle refused"}) + "\n",
        encoding="utf-8",
    )
    (tmp / "unresolved_models.jsonl").write_text(
        "\n".join(
            json.dumps({"at": _now(1), "name": name, "source": "releases/OpenAI — News"})
            for name in ("Introducing the Agents API", "Credentio", "Credentio")
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp / "queue.json").write_text(
        json.dumps({"items": [
            {"channel": "releases", "title": "A release that missed the budget",
             "entity": "openai/gpt-astra/6/new_model", "score": 11.0,
             "queuedAt": _now(1)},
            {"channel": "releases", "title": "Another one", "entity": "google/gemini-flash/3.7/new_model",
             "score": 8.0, "queuedAt": _now(1)},
        ]}),
        encoding="utf-8",
    )


def _render_with_synthetic_state(ledger) -> str:
    tmp = Path(tempfile.mkdtemp())
    _seed(tmp)
    originals = (
        report_module.REJECTED_FILE,
        report_module.ADAPTER_FAILURES_FILE,
        report_module.UNRESOLVED_MODELS_FILE,
        report_module.QUEUE_FILE,
    )
    report_module.REJECTED_FILE = tmp / "rejected.jsonl"
    report_module.ADAPTER_FAILURES_FILE = tmp / "adapter_failures.jsonl"
    report_module.UNRESOLVED_MODELS_FILE = tmp / "unresolved_models.jsonl"
    report_module.QUEUE_FILE = tmp / "queue.json"
    try:
        return report_module.render(ledger)
    finally:
        (
            report_module.REJECTED_FILE,
            report_module.ADAPTER_FAILURES_FILE,
            report_module.UNRESOLVED_MODELS_FILE,
            report_module.QUEUE_FILE,
        ) = originals


def test_report_contains_every_required_section():
    ledger = _FakeLedger(_entries("research", 4, 2) + _entries("release", 3, 4))
    text = _render_with_synthetic_state(ledger)
    for heading in (
        "PUBLISHED / TARGET",
        "REJECTED — quality",
        "REJECTED — budget",
        "ADAPTER FAILURES",
        "UNRESOLVED MODEL NAMES",
        "TOP QUEUED, NOT PUBLISHED",
        "EXCLUDED — the owner's exclude[] list",
        "DISCOVERY MIX",
        "TOPICS LONGEST UNTOUCHED",
    ):
        assert heading in text, heading


def test_published_counts_are_per_section_and_against_target():
    ledger = _FakeLedger(_entries("research", 4, 2) + _entries("release", 3, 4))
    text = _render_with_synthetic_state(ledger)
    assert "research      4 / 6" in text
    assert "release       3 / 6" in text
    assert "benchmark     0 / 2" in text
    assert "GLOBAL        7 / 50" in text


def test_quality_and_budget_drops_are_reported_separately():
    """§8's insistence: the two are different events. A report that
    merged them would hide the difference between a channel doing its
    job and a channel being throttled."""
    ledger = _FakeLedger([])
    text = _render_with_synthetic_state(ledger)
    quality = text.split("REJECTED — quality")[1].split("REJECTED — budget")[0]
    budget = text.split("REJECTED — budget")[1].split("ADAPTER FAILURES")[0]
    assert "not_a_release" in quality
    assert "gate_g1_ungrounded_number" in quality
    assert "section_budget_exhausted" in budget
    assert "section_budget_exhausted" not in quality
    assert "not_a_release" not in budget


def test_gate_rejections_are_visible_by_gate():
    """Which gate is firing is the difference between "the model is
    inventing numbers" and "the source scraper is broken"."""
    text = _render_with_synthetic_state(_FakeLedger([]))
    assert "gate_g1_ungrounded_number" in text


def test_only_the_rolling_window_is_counted():
    text = _render_with_synthetic_state(_FakeLedger([]))
    assert "duplicate_url" not in text, "a 30-day-old rejection is not this week's news"


def test_unresolved_names_are_deduplicated_and_labelled_as_parked():
    text = _render_with_synthetic_state(_FakeLedger([]))
    section = text.split("UNRESOLVED MODEL NAMES")[1]
    assert section.count("Credentio") == 1
    assert "Nothing auto-registers" in section


def test_adapter_failures_are_reported_not_fatal():
    text = _render_with_synthetic_state(_FakeLedger([]))
    assert "lmarena" in text.split("ADAPTER FAILURES")[1]


def test_top_three_queued_items_are_shown_highest_first():
    text = _render_with_synthetic_state(_FakeLedger([]))
    section = text.split("TOP QUEUED, NOT PUBLISHED")[1]
    assert "11.0" in section
    assert section.index("11.0") < section.index("8.0")


def test_hitting_the_global_cap_reads_as_an_incident():
    """Not routine truncation. It means a threshold is set too low."""
    ledger = _FakeLedger(_entries("news", 50, 1))
    text = _render_with_synthetic_state(ledger)
    assert "INCIDENT" in text
    assert "threshold is set too low" in text


def test_report_fits_in_one_telegram_message():
    """A report that fails to send is worse than a short one."""
    ledger = _FakeLedger(_entries("news", 20, 1) + _entries("releases", 8, 1))
    text = _render_with_synthetic_state(ledger)
    assert len(text) <= report_module.TELEGRAM_LIMIT, len(text)


def test_generating_a_report_sends_nothing():
    """Observability, not a review step — and generating it must be
    free of side effects, or it cannot be inspected without messaging
    somebody."""
    sent = []
    original = report_module.send
    report_module.send = lambda text: sent.append(text)
    try:
        _render_with_synthetic_state(_FakeLedger([]))
    finally:
        report_module.send = original
    assert sent == []
