"""
Feedback actions (brief §11.2).

| action          | meaning                  | effect                       |
|-----------------|--------------------------|------------------------------|
| 👍 interesting  | valuable                 | +1 to item and its topics    |
| 👎 not useful   | this piece was weak      | −1 to item; NOT the topic    |
| 🚫 not my topic | wrong subject            | −3 to the topic profile      |
| ⭐ deep dive    | worth going deeper       | +3 to topic; queue a piece   |
| 🗑 retract      | should not have shipped  | −3 AND unpublish             |

**Feedback is steering, not gating.** It arrives after publication and
never blocks it. Nothing in this module can hold a post back and nothing
in the pipeline waits on it.

THE DISTINCTION THAT MATTERS is 👎 versus 🚫. A 👎 says "this piece was
weak" and must not be read as "this subject is wrong" — a good topic
covered badly is a drafting problem, and letting it demote the topic
would teach the profile the opposite of what happened. So 👎 is scoped
to the ITEM and 🚫 is scoped to the TOPIC, and they carry different
weights. The whole point of §11.3's `min_observations` is that one
reaction never moves anything anyway.

EVERY REACTION IS APPENDED TO state/feedback.jsonl, FOREVER. §11.3 calls
it the training data for any better ranking later and notes that it
cannot be reconstructed. Nothing here rewrites or prunes it;
aggregation happens on read.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.constants import FEEDBACK_FILE
from core.profile import profile as load_profile_object
from core.radar import Radar
from core.state import read_jsonl, record_feedback

# The five actions, and the two scopes. Weights come from
# interest_profile.yaml so they are tunable without a code change; these
# are the fallbacks if the file is silent.
DEFAULT_WEIGHTS = {
    "interesting": {"weight": 1, "scope": "item"},
    "not_useful": {"weight": -1, "scope": "item"},
    "not_my_topic": {"weight": -3, "scope": "topic"},
    "deep_dive": {"weight": 3, "scope": "topic"},
    "retract": {"weight": -3, "scope": "item", "action": "unpublish"},
}

ACTIONS = tuple(DEFAULT_WEIGHTS)


def weights() -> dict:
    configured = (load_profile_object().feedback or {}).get("kinds") or {}
    merged = {k: dict(v) for k, v in DEFAULT_WEIGHTS.items()}
    for kind, spec in configured.items():
        if kind in merged and isinstance(spec, dict):
            merged[kind].update(spec)
    return merged


@dataclass
class Outcome:
    action: str
    item_id: str
    accepted: bool
    detail: str
    retracted_slug: str | None = None


def parse_callback(data: str) -> tuple[str, str] | None:
    """"<action>:<candidateId>" -> (action, id), or None.

    Strict: an unrecognised action is not guessed at. A malformed
    callback is almost always a stale button from an older message
    format, and acting on a guess would apply the wrong signal to a real
    item."""
    if not data or ":" not in data:
        return None
    action, _, item_id = data.partition(":")
    if action not in ACTIONS or not item_id:
        return None
    return action, item_id


def apply(
    action: str,
    item_id: str,
    *,
    radar: Radar,
    dry_run: bool = True,
    repo_root=None,
) -> Outcome:
    """Record one reaction and carry out its effect.

    Returns an Outcome rather than raising: a reaction to an item that
    has aged out of the Radar is a normal thing to happen months later,
    not an error, and the owner should get a readable answer rather
    than a stack trace.
    """
    if action not in ACTIONS:
        return Outcome(action, item_id, False, f"unknown action {action!r}")

    item = radar.find(item_id)
    section = item.get("section", "") if item else ""
    topics = item.get("topics", []) if item else []
    slug = (item or {}).get("promotedTo", "")

    # The permanent record comes first, before any effect, so a failure
    # in the effect cannot lose the signal.
    record_feedback(
        item_id, action, section=section, topics=topics, slug=slug, dry_run=dry_run
    )

    if item is None:
        return Outcome(
            action, item_id, True,
            "recorded, but the item is no longer on the Radar — the signal "
            "still counts toward the profile.",
        )

    if action == "retract":
        from telegram import retract as retract_module

        result = retract_module.retract(
            item, radar=radar, dry_run=dry_run, repo_root=repo_root
        )
        return Outcome(action, item_id, result.ok, result.detail,
                       retracted_slug=result.slug)

    radar.set_feedback(item_id, action)
    if action == "deep_dive":
        # §11.2: ⭐ also queues the item for a Fundamentals or deepdive
        # piece. §6 calls this promotion, and it is the mechanism by
        # which a Radar item becomes a post days after it was first
        # seen — the only path into Fundamentals, which §8.6 says is not
        # feed-driven.
        return Outcome(action, item_id, True,
                       "+3 to its topics and queued for a deeper piece.")

    spec = weights()[action]
    scope = spec["scope"]
    target = "its topics" if scope == "topic" else "this item only"
    return Outcome(action, item_id, True,
                   f"{spec['weight']:+d} to {target}.")


# --- reading the accumulated signal (input to Phase 8) ---------------


def history(days: int | None = None) -> list[dict]:
    rows = list(read_jsonl(FEEDBACK_FILE))
    if days is None:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for row in rows:
        try:
            when = datetime.fromisoformat(row["at"])
        except (KeyError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            out.append(row)
    return out


def topic_signal(rows: list[dict] | None = None) -> dict[str, dict]:
    """Net signal per topic, plus how many rated items it rests on.

    The observation count is separate from the score on purpose: §11.3
    will not move a topic on fewer than `min_observations` rated items
    however strong the net signal looks, and collapsing the two into one
    number would hide that.

    ITEM-SCOPED reactions (👍 👎 🗑) count as observations of a topic but
    contribute NO score to it. That is the §11.2 distinction made
    arithmetic: a weak piece is evidence that the topic was covered
    badly, not that the topic is wrong.
    """
    rows = history() if rows is None else rows
    spec = weights()
    signal: dict[str, dict] = defaultdict(lambda: {"net": 0, "observations": 0,
                                                   "actions": defaultdict(int)})
    for row in rows:
        action = row.get("kind")
        if action not in spec:
            continue
        for topic in row.get("topics") or []:
            entry = signal[topic]
            entry["observations"] += 1
            entry["actions"][action] += 1
            if spec[action]["scope"] == "topic":
                entry["net"] += int(spec[action]["weight"])
    return {t: {**v, "actions": dict(v["actions"])} for t, v in signal.items()}


def item_signal(rows: list[dict] | None = None) -> dict[str, int]:
    """Net signal per item. Not used for ranking — it is here because
    §11.3 says the raw history is training data for a better ranking
    later, and the per-item view is the shape that would need."""
    rows = history() if rows is None else rows
    spec = weights()
    out: dict[str, int] = defaultdict(int)
    for row in rows:
        action = row.get("kind")
        if action in spec:
            out[row.get("itemId", "")] += int(spec[action]["weight"])
    return dict(out)


# --- the polling loop ------------------------------------------------


def handle_updates(updates: list[dict], *, radar: Radar, dry_run: bool = True) -> list[Outcome]:
    """Turn Telegram callback queries into Outcomes.

    NOT WIRED TO A SCHEDULE. No workflow calls this, and the transport
    it would need refuses to send without an explicit --send that
    nothing passes. It exists so that turning the loop on is wiring
    rather than writing.
    """
    outcomes = []
    for update in updates:
        query = update.get("callback_query")
        if not query:
            continue
        parsed = parse_callback(query.get("data", ""))
        if parsed is None:
            continue
        action, item_id = parsed
        outcome = apply(action, item_id, radar=radar, dry_run=dry_run)
        outcomes.append(outcome)
        if not dry_run:
            from telegram import api

            api.answer_callback(query.get("id", ""), outcome.detail)
    return outcomes
