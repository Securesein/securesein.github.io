"""
Every file the pipeline reads back on its next run.

Two shapes, and the difference matters:

  state/*.json   current state — the ledger, the entity cooldowns, the
                 queue. Rewritten in place; small; committed.
  state/*.jsonl  append-only logs — rejections, unresolved model names,
                 adapter failures. Never rewritten, so a run can never
                 quietly lose the record of what it dropped.

A drop for *budget* reasons and a drop for *quality* reasons are
different events (brief §8) and are written with different reasons, so
"we stopped publishing because the rubric got stricter" and "we stopped
publishing because we ran out of week" never look alike in the weekly
report.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .constants import (
    REJECTED_FILE,
    STATE_DIR,
    UNRESOLVED_MODELS_FILE,
    ADAPTER_FAILURES_FILE,
    FEEDBACK_FILE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt state file must not take the run down: the worst
        # case of starting from empty is re-publishing something, which
        # the entity cooldown and the archive dedup both catch.
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return iter(())

    def rows() -> Iterator[dict]:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    return rows()


# --- the three append-only logs, each with its own vocabulary --------

# Quality reasons: the item was not good enough, or not what this
# channel is for. Budget reasons: the item was fine and there was no
# room. Keeping these apart is what makes a threshold tunable.
QUALITY_REASONS = {
    "below_quality_gate",      # stage 1 of §7.1 — the pass/fail gate
    "below_threshold",
    "not_a_release",
    "no_product_angle",
    "press_release_only",
    "unresolved_vendor",
    "unresolved_model",
    "duplicate_url",
    "duplicate_title",
    "entity_covered",
    "non_primary_source",
    "roundup_only_source",     # §8.3 — never publish from a roundup alone
    "gate_g1_ungrounded_number",
    "gate_g2_entity_not_in_source",
    "gate_g3_verifier_rejected",
    "gate_g5_dangling_reference",
    "no_valid_topic",
    "wrong_section",
    "relevance_gate",
    "stale",
}
# The exclusion filter (§7) is neither: an excluded item is not low
# quality and there was nothing wrong with the budget — the owner said
# in advance not to look at this kind of thing at all. Keeping it apart
# is what stops "we excluded 40 funding stories" reading like "the
# quality bar rose".
EXCLUSION_REASONS = {"profile_excluded"}
BUDGET_REASONS = {
    "section_budget_exhausted",
    "global_cap_reached",
    "per_run_cap",
    "per_day_cap",
    "queue_expired",
}


def reject(
    channel: str,
    reason: str,
    *,
    title: str = "",
    url: str = "",
    score: float | None = None,
    detail: Any = None,
    dry_run: bool = False,
) -> None:
    """One line in state/rejected.jsonl per drop, always. The gates
    write the offending content into `detail` so a rejection can be
    understood months later without re-fetching the source."""
    append_jsonl(
        REJECTED_FILE,
        {
            "at": now_iso(),
            "channel": channel,
            "reason": reason,
            "class": (
                "budget"
                if reason in BUDGET_REASONS
                else "exclusion"
                if reason in EXCLUSION_REASONS
                else "quality"
            ),
            "title": title,
            "url": url,
            "score": score,
            "detail": detail,
            "dryRun": dry_run,
        },
    )


def park_unresolved_model(name: str, source: str, **extra: Any) -> None:
    """§4.1: an unresolved model name is parked, never auto-registered
    and never written into the collection. This file is the input to the
    weekly report and, eventually, to a human editing models.json."""
    append_jsonl(
        UNRESOLVED_MODELS_FILE,
        {"at": now_iso(), "name": name, "source": source, **extra},
    )


def log_adapter_failure(adapter: str, error: str) -> None:
    """§7.1: each adapter is independent and wrapped — one broken
    scraper must never stop the Epoch pull landing. The failure goes
    here and into the weekly report instead of into the exit code."""
    append_jsonl(
        ADAPTER_FAILURES_FILE, {"at": now_iso(), "adapter": adapter, "error": error}
    )


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def record_feedback(
    item_id: str,
    kind: str,
    *,
    section: str = "",
    topics: list | None = None,
    slug: str = "",
    dry_run: bool = False,
) -> None:
    """One line in state/feedback.jsonl per reaction, forever.

    §11.3 is explicit that this file is permanent raw history: it is the
    training data for any better ranking later and it cannot be
    reconstructed, so nothing in this pipeline ever rewrites or prunes
    it. Aggregation happens on read.
    """
    append_jsonl(
        FEEDBACK_FILE,
        {
            "at": now_iso(),
            "itemId": item_id,
            "slug": slug,
            "kind": kind,
            "section": section,
            "topics": topics or [],
            "dryRun": dry_run,
        },
    )
