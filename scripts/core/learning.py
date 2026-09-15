"""
Profile learning (brief §11.3) — PROPOSALS ONLY.

    python scripts/run.py --propose

    ############################################################
    #  THIS MODULE CANNOT WRITE interest_profile.yaml.         #
    #                                                          #
    #  Not "does not by default" — cannot. There is no write   #
    #  path in this file, no yaml.dump anywhere in the repo,   #
    #  and INTEREST_PROFILE_FILE is opened for reading in      #
    #  exactly one place (core/profile.load_profile).          #
    #  scripts/tests/test_learning.py asserts all three across #
    #  the whole scripts/ tree, so adding one later fails the  #
    #  suite rather than quietly shipping.                     #
    #                                                          #
    #  §11.3: "Scout proposes; the owner approves. Never       #
    #  auto-edit interest_profile.yaml without confirmation."  #
    #  A proposal is something a human applies by hand. There  #
    #  is no --apply flag and this build does not add one.     #
    ############################################################

FOUR RULES, and every one of them exists to stop the profile collapsing
onto whatever the owner happened to react to last month:

  min_observations: 10   a topic with fewer than ten RATED items cannot
                         move at all, however strong the net signal
                         looks. Three enthusiastic taps are not evidence.
  promotion_threshold: 8 / demotion_threshold: -8
                         net signal, counting only TOPIC-scoped
                         reactions (🚫 and ⭐). A 👎 on a weak piece is
                         not evidence against its subject — see
                         telegram/feedback.py.
  floor: at least five topics stay at `strong`. Without it the profile
                         narrows to one subject within months, which is
                         the failure §11.3 names.
  exclude[] is owner-only. Nothing here ever proposes an addition to it,
                         and `never_auto_exclude` is checked rather than
                         assumed.

The raw history in state/feedback.jsonl is permanent and is never
rewritten or pruned by anything — it is the training data for any better
ranking later and it cannot be reconstructed. Everything here is
computed on read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import taxonomy as tax
from .constants import PROFILE_PROPOSALS_FILE
from .profile import Profile, profile as load_profile_object
from .state import append_jsonl, now_iso

# Fallbacks if the profile is silent. The profile is the authority.
DEFAULTS = {
    "min_observations": 10,
    "promotion_threshold": 8,
    "demotion_threshold": -8,
    "min_topics_at_strong": 5,
    "never_auto_exclude": True,
}


def rules(prof: Profile | None = None) -> dict:
    prof = prof or load_profile_object()
    config = prof.feedback or {}
    floor = config.get("floor") or {}
    return {
        "min_observations": int(config.get("min_observations",
                                           DEFAULTS["min_observations"])),
        "promotion_threshold": int(config.get("promotion_threshold",
                                              DEFAULTS["promotion_threshold"])),
        "demotion_threshold": int(config.get("demotion_threshold",
                                             DEFAULTS["demotion_threshold"])),
        "min_topics_at_strong": int(floor.get("min_topics_at_strong",
                                              DEFAULTS["min_topics_at_strong"])),
        "never_auto_exclude": bool(floor.get("never_auto_exclude",
                                             DEFAULTS["never_auto_exclude"])),
        "requires_confirmation": bool(config.get("requires_confirmation", True)),
    }


@dataclass
class Change:
    """One proposed edit, with everything needed to argue with it."""

    topic: str
    direction: str          # "promote" | "demote"
    net: int
    observations: int
    breakdown: dict = field(default_factory=dict)
    rationale: str = ""

    def as_dict(self) -> dict:
        return {
            "topic": self.topic,
            "direction": self.direction,
            "net": self.net,
            "observations": self.observations,
            "breakdown": self.breakdown,
            "rationale": self.rationale,
        }


@dataclass
class Proposal:
    generatedAt: str
    changes: list[Change] = field(default_factory=list)
    withheld: list[dict] = field(default_factory=list)
    considered: int = 0

    def as_dict(self) -> dict:
        return {
            "generatedAt": self.generatedAt,
            "changes": [c.as_dict() for c in self.changes],
            "withheld": self.withheld,
            "considered": self.considered,
            # Stated in the artefact itself, not only in this file's
            # docstring, so a proposal read out of the log in six months
            # still says what it is.
            "applied": False,
            "note": (
                "PROPOSAL ONLY. Scout proposes; the owner approves. Nothing "
                "in this repository can write interest_profile.yaml — apply "
                "any of this by hand, or not at all."
            ),
        }


def _strong_topic_count(prof: Profile) -> int:
    """How many of the CLOSED-vocabulary topics the strong interests
    currently reach.

    The profile's strong_interests are prose entries ("mechanistic
    interpretability") rather than taxonomy slugs, so the floor is
    measured the same way the ranking measures a match: through the
    signal phrases against each topic's own label and description. Two
    vocabularies written for the same site, compared on their own
    terms — the same approach core/profile._topic_vocabulary takes.
    """
    reached = set()
    for topic_slug, info in tax.topics().items():
        haystack = f"{info['label']} {info['description']}".lower()
        for _, phrases in prof.strong:
            if any(p in haystack for p in phrases):
                reached.add(topic_slug)
                break
    return len(reached)


def propose(signal: dict[str, dict] | None = None,
            prof: Profile | None = None) -> Proposal:
    """Turn accumulated feedback into a proposed set of profile changes.

    `signal` is telegram/feedback.topic_signal()'s output. Passed in
    rather than fetched so this is a pure function of its inputs and can
    be tested without a feedback log.
    """
    prof = prof or load_profile_object()
    config = rules(prof)
    if signal is None:
        from telegram import feedback as feedback_module

        signal = feedback_module.topic_signal()

    proposal = Proposal(generatedAt=now_iso(), considered=len(signal))
    strong_now = _strong_topic_count(prof)

    for topic, row in sorted(signal.items()):
        net, observations = int(row["net"]), int(row["observations"])
        breakdown = row.get("actions", {})

        if observations < config["min_observations"]:
            proposal.withheld.append({
                "topic": topic, "net": net, "observations": observations,
                "reason": (
                    f"only {observations} rated item(s); "
                    f"min_observations is {config['min_observations']}. "
                    f"One reaction never moves the profile."
                ),
            })
            continue

        if net >= config["promotion_threshold"]:
            proposal.changes.append(Change(
                topic=topic, direction="promote", net=net,
                observations=observations, breakdown=breakdown,
                rationale=(
                    f"net +{net} across {observations} rated items, at or "
                    f"above promotion_threshold {config['promotion_threshold']}."
                ),
            ))
        elif net <= config["demotion_threshold"]:
            # THE FLOOR. Demoting below five strong topics is how a
            # profile collapses onto one subject, so the proposal is
            # withheld with its reason rather than made and then argued
            # about.
            pending_demotions = sum(
                1 for c in proposal.changes if c.direction == "demote"
            )
            if strong_now - pending_demotions - 1 < config["min_topics_at_strong"]:
                proposal.withheld.append({
                    "topic": topic, "net": net, "observations": observations,
                    "reason": (
                        f"demoting it would leave fewer than "
                        f"{config['min_topics_at_strong']} topics at strong "
                        f"({strong_now} now). The floor exists because without "
                        f"it the profile narrows to one subject within months."
                    ),
                })
                continue
            proposal.changes.append(Change(
                topic=topic, direction="demote", net=net,
                observations=observations, breakdown=breakdown,
                rationale=(
                    f"net {net} across {observations} rated items, at or below "
                    f"demotion_threshold {config['demotion_threshold']}."
                ),
            ))
        else:
            proposal.withheld.append({
                "topic": topic, "net": net, "observations": observations,
                "reason": (
                    f"net {net:+d} is inside the dead band "
                    f"({config['demotion_threshold']}.."
                    f"{config['promotion_threshold']}) — not enough signal "
                    f"either way."
                ),
            })

    return proposal


def render(proposal: Proposal, prof: Profile | None = None) -> str:
    """The proposal as something a person reads and then decides about.

    Deliberately NOT a patch file, and deliberately not machine-
    appliable. A diff invites `git apply`; this invites a decision.
    """
    prof = prof or load_profile_object()
    config = rules(prof)
    lines = ["Scout — proposed profile changes"]
    lines.append(
        f"(from {proposal.considered} topic(s) with any feedback; "
        f"min_observations {config['min_observations']}, thresholds "
        f"{config['promotion_threshold']:+d}/{config['demotion_threshold']:+d})"
    )
    lines.append("")
    lines.append("NOTHING HAS BEEN CHANGED. This is a proposal; edit")
    lines.append("interest_profile.yaml by hand if you agree with it.")
    lines.append("")

    if proposal.changes:
        lines.append("PROPOSED")
        for change in proposal.changes:
            arrow = "↑ promote" if change.direction == "promote" else "↓ demote"
            lines.append(f"  {arrow}  {change.topic}")
            lines.append(f"      {change.rationale}")
            if change.breakdown:
                detail = ", ".join(
                    f"{k} x{v}" for k, v in sorted(change.breakdown.items())
                )
                lines.append(f"      reactions: {detail}")
        lines.append("")
    else:
        lines.append("PROPOSED")
        lines.append("  (nothing — no topic has accumulated enough signal)")
        lines.append("")

    if proposal.withheld:
        lines.append("WITHHELD, and why")
        for row in proposal.withheld[:10]:
            lines.append(f"  {row['topic']}: {row['reason']}")
        if len(proposal.withheld) > 10:
            lines.append(f"  ...and {len(proposal.withheld) - 10} more")
        lines.append("")

    lines.append("NEVER PROPOSED, BY RULE")
    lines.append("  · additions to exclude[] — owner-only (§11.3).")
    lines.append(f"  · any demotion that would leave fewer than "
                 f"{config['min_topics_at_strong']} topics at strong.")
    lines.append("  · anything at all, automatically. There is no --apply.")
    return "\n".join(lines) + "\n"


def record(proposal: Proposal, *, dry_run: bool = True) -> None:
    """Append the proposal to state/profile_proposals.jsonl.

    This writes a LOG of what was proposed. It does not, and cannot,
    write the profile. The two files are different by design: one is a
    record of what Scout suggested, the other is what the owner
    actually believes, and only a person moves a line from the first to
    the second.
    """
    if dry_run:
        print("    [dry-run] proposal not recorded.")
        return
    append_jsonl(PROFILE_PROPOSALS_FILE, proposal.as_dict())


def as_json(proposal: Proposal) -> str:
    return json.dumps(proposal.as_dict(), ensure_ascii=False, indent=2)
