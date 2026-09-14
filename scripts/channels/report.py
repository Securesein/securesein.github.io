"""
The weekly observability report (brief §13).

    python scripts/run.py --report               # print it
    python scripts/run.py --report --send        # print AND send it

Six things, and they are the six things you cannot see any other way
once a pipeline publishes without review:

  1. published per section
  2. rejected, counted by reason — with QUALITY and BUDGET drops
     separated, because "the rubric got stricter" and "we ran out of
     week" are different problems wearing the same number
  3. budget consumed against target, and whether the global circuit
     breaker was hit (an incident, not a truncation)
  4. adapter failures
  5. unresolved model names, which is the queue of registry work
  6. the top three queued items that did not make it
  7. the discovery mix — the ~70/20/10 strong/adjacent/serendipity
     split, which §7.1 says is checked WEEKLY and never per run
  8. topic starvation — which topics have gone longest untouched, the
     input to the ranking bonus of the same name

**This is observability, not a review step. Nothing waits on a reply.**
The report is sent, and the next run happens whether anyone reads it or
not. A report that could block a publication would be a human approval
gate with extra steps, which the brief rules out.

--send is opt-in and is NOT passed by anything in this repo. Generating
the report is free and harmless; sending it is a side effect, and side
effects are opt-in here for the same reason publishing is.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from core import taxonomy as tax
from core.constants import (
    ADAPTER_FAILURES_FILE,
    QUEUE_FILE,
    REJECTED_FILE,
    UNRESOLVED_MODELS_FILE,
)
from core.ledger import Ledger
from core.profile import TopicActivity, discovery_mix, profile as load_profile_object
from core.state import read_json, read_jsonl

WINDOW_DAYS = 7
# Telegram refuses anything over 4096 characters, and a report that
# fails to send is worse than a short one.
TELEGRAM_LIMIT = 4000


def _within_window(row: dict, field: str = "at") -> bool:
    try:
        when = datetime.fromisoformat(row[field])
    except (KeyError, ValueError, TypeError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when >= datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)


def gather(ledger: Ledger) -> dict:
    rejections = [r for r in read_jsonl(REJECTED_FILE) if _within_window(r)]
    failures = [r for r in read_jsonl(ADAPTER_FAILURES_FILE) if _within_window(r)]
    unresolved = [r for r in read_jsonl(UNRESOLVED_MODELS_FILE) if _within_window(r)]
    queue = read_json(QUEUE_FILE, {"items": []})["items"]

    return {
        "budget": ledger.summary(),
        "published": Counter(
            entry.get("section", entry.get("channel", "?"))
            for entry in ledger._rows_since(  # noqa: SLF001
                datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
            )
        ),
        "quality": Counter(
            r["reason"] for r in rejections if r.get("class") == "quality"
        ),
        "budget_drops": Counter(
            r["reason"] for r in rejections if r.get("class") == "budget"
        ),
        "failures": Counter(r["adapter"] for r in failures),
        # One entry per distinct name, in first-seen order: the same
        # unregistered model turns up on every run until someone deals
        # with it, and a report that listed it forty times would be
        # ignored.
        "unresolved": list(dict.fromkeys(r["name"] for r in unresolved)),
        "queue": sorted(queue, key=lambda i: i.get("score", 0), reverse=True),
        "incident": ledger.used() >= ledger.hard_cap(),
        "exclusions": Counter(
            str(r.get("detail"))
            for r in rejections
            if r.get("class") == "exclusion"
        ),
        # §7.1: checked weekly, not per run. Nothing acts on it — it is
        # reported so a filter bubble becomes visible before it becomes
        # a habit.
        "discovery": discovery_mix(_radar_buckets()),
        "starvation": TopicActivity(load_profile_object()).starved(tax.topic_slugs()),
    }


def _radar_buckets() -> list[dict]:
    """Every Radar item seen in the window, with the interest bucket it
    landed in. Read from the Radar rather than from the ledger because
    the mix is about what the pipeline CONSIDERED, and a week in which
    nothing was published still has a discovery mix."""
    from core.radar import Radar

    rows = []
    for item in Radar(dry_run=True).since(hours=WINDOW_DAYS * 24):
        relevance = item.get("relevanceScore", 0)
        # Reconstructed from the score rather than stored: a strong
        # match is worth 45 and a medium one 20, so the bands are
        # unambiguous without a second field on every record.
        bucket = ("strong" if relevance >= 45 else
                  "adjacent" if relevance >= 20 else "serendipity")
        rows.append({"bucket": bucket})
    return rows


def render(ledger: Ledger) -> str:
    data = gather(ledger)
    lines: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y")
    lines.append(f"securesein — weekly pipeline report, {stamp}")
    lines.append(f"(rolling {WINDOW_DAYS} days)")
    lines.append("")

    # 1 + 3: published, against target.
    lines.append("PUBLISHED / TARGET")
    for section, budget in data["budget"]["sections"].items():
        published = data["published"].get(section, 0)
        bar = "at target" if published >= budget["target"] else f"{budget['target'] - published} left"
        lines.append(f"  {section:<11} {published:>3} / {budget['target']:<3}  {bar}")
    total = data["budget"]["global"]
    lines.append(f"  {'GLOBAL':<11} {total['used']:>3} / {total['cap']:<3}  circuit breaker")
    if data["incident"]:
        lines.append("")
        lines.append("  *** INCIDENT: the global cap was reached. This should")
        lines.append("      never happen in normal operation — it means a")
        lines.append("      channel threshold is set too low. Raise it before")
        lines.append("      the next run rather than treating this as routine.")
    lines.append("")

    # 2: rejections, with the two classes kept apart.
    lines.append("REJECTED — quality")
    if data["quality"]:
        for reason, count in data["quality"].most_common(10):
            lines.append(f"  {count:>4}  {reason}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("REJECTED — budget (good items, no room)")
    if data["budget_drops"]:
        for reason, count in data["budget_drops"].most_common():
            lines.append(f"  {count:>4}  {reason}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("EXCLUDED — the owner's exclude[] list (never scored)")
    if data["exclusions"]:
        for line, count in data["exclusions"].most_common(5):
            lines.append(f"  {count:>4}  {line[:62]}")
    else:
        lines.append("  (none)")
    lines.append("")

    # 4: adapter failures.
    lines.append("ADAPTER FAILURES")
    if data["failures"]:
        for adapter, count in data["failures"].most_common():
            lines.append(f"  {count:>4}  {adapter}")
    else:
        lines.append("  (none)")
    lines.append("")

    # 5: the registry work queue.
    lines.append(f"UNRESOLVED MODEL NAMES ({len(data['unresolved'])})")
    if data["unresolved"]:
        for name in data["unresolved"][:10]:
            lines.append(f"  {name[:70]}")
        if len(data["unresolved"]) > 10:
            lines.append(f"  ...and {len(data['unresolved']) - 10} more")
        lines.append("  (park -> models.json, or ignore. Nothing auto-registers.)")
    else:
        lines.append("  (none)")
    lines.append("")

    # 6: what budget kept out.
    lines.append("TOP QUEUED, NOT PUBLISHED")
    if data["queue"]:
        for item in data["queue"][:3]:
            lines.append(
                f"  {item.get('score', 0):>5.1f}  {str(item.get('title', ''))[:58]}"
            )
            lines.append(f"         {item.get('entity', item.get('channel', ''))}")
    else:
        lines.append("  (queue empty)")
    lines.append("")

    # 7: the discovery mix. Target is roughly 70/20/10.
    mix = data["discovery"]
    lines.append(f"DISCOVERY MIX (n={mix.get('n', 0)}, target 70/20/10)")
    if mix.get("n"):
        shares = mix["shares"]
        lines.append(
            f"  strong {shares['strong']:.0%} · adjacent {shares['adjacent']:.0%} "
            f"· serendipity {shares['serendipity']:.0%}"
        )
        lines.append("  (reported only — nothing in the pipeline acts on this)")
    else:
        lines.append("  (nothing considered this week)")
    lines.append("")

    # 8: topic starvation.
    lines.append("TOPICS LONGEST UNTOUCHED")
    for topic, days in data["starvation"][:5]:
        when = "never published" if days < 0 else f"{days}d ago"
        lines.append(f"  {topic:<24} {when}")

    return "\n".join(lines)


def send(text: str) -> bool:
    """Telegram only, no publication. Kept behind an explicit flag: a
    report that sends itself as a side effect of being generated makes
    the report impossible to inspect without messaging someone."""
    import telegram_api

    body = text if len(text) <= TELEGRAM_LIMIT else text[: TELEGRAM_LIMIT - 20] + "\n…(truncated)"
    result = telegram_api.send_message(body)
    return bool(result and result.get("ok"))


def as_json(ledger: Ledger) -> str:
    data = gather(ledger)
    data["published"] = dict(data["published"])
    data["quality"] = dict(data["quality"])
    data["budget_drops"] = dict(data["budget_drops"])
    data["failures"] = dict(data["failures"])
    data["exclusions"] = dict(data["exclusions"])
    data["queue"] = data["queue"][:3]
    return json.dumps(data, ensure_ascii=False, indent=2)
