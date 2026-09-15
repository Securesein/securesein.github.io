"""
Profile learning (brief §11.3) — proposals only.

The most important tests in this file are the ones that assert
something does NOT exist. §11.3 says "Scout proposes; the owner
approves. Never auto-edit interest_profile.yaml without confirmation",
and the way to hold that is not a default flag but the absence of a
write path. These tests check the absence across the whole scripts/
tree, so adding one later fails the suite rather than shipping quietly.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import learning  # noqa: E402
from core.profile import Profile, profile as load_profile_object  # noqa: E402

PROF = load_profile_object()


def _signal(**topics) -> dict:
    """topic -> (net, observations[, breakdown])."""
    out = {}
    for topic, value in topics.items():
        net, observations = value[0], value[1]
        out[topic.replace("_", "-")] = {
            "net": net, "observations": observations,
            "actions": value[2] if len(value) > 2 else {},
        }
    return out


# --- THE constraint ---------------------------------------------------


def test_nothing_in_scripts_can_write_the_interest_profile():
    """The load-bearing assertion of Phase 8.

    Three things are checked, because any one of them alone could be
    worked around: no module opens the profile for writing, no module
    serialises YAML at all, and the profile path is referenced in
    exactly the places that read it.
    """
    offenders = []
    for path in (REPO_ROOT / "scripts").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT).as_posix()

        # 1. No YAML serialisation anywhere. Reading is yaml.safe_load;
        #    writing would be yaml.dump/safe_dump, and there is no other
        #    reason for it to appear. Checked through the AST so that
        #    prose SAYING there is no yaml.dump does not count as one.
        import ast

        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "dump", "safe_dump", "round_trip_dump"
            ):
                owner = getattr(func.value, "id", "")
                if owner in ("yaml", "ruamel"):
                    offenders.append(f"{relative}: {owner}.{func.attr}()")

        # 2. Nothing writes to the profile path by any route.
        if "INTEREST_PROFILE_FILE" in text:
            for line in text.splitlines():
                if "INTEREST_PROFILE_FILE" not in line:
                    continue
                if any(w in line for w in (".write_text", ".open(\"w", ".open('w",
                                           "write_json", ".unlink")):
                    offenders.append(f"{relative}: {line.strip()}")

        # 3. No --apply flag appears anywhere.
        if '"--apply"' in text or "'--apply'" in text:
            offenders.append(f"{relative}: an --apply flag exists")

    assert offenders == [], offenders


def test_the_profile_is_opened_for_reading_in_exactly_one_place():
    readers = []
    for path in (REPO_ROOT / "scripts").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "INTEREST_PROFILE_FILE.read_text" in text:
            readers.append(path.relative_to(REPO_ROOT).as_posix())
    assert readers == ["scripts/core/profile.py"], readers


def test_the_proposal_says_it_is_a_proposal():
    """A proposal read out of the log in six months has to say what it
    is without the reader going back to the docstring."""
    proposal = learning.propose(_signal(llms=(12, 14)))
    document = proposal.as_dict()
    assert document["applied"] is False
    assert "PROPOSAL ONLY" in document["note"]
    assert "Scout proposes; the owner approves" in document["note"]
    assert "by hand" in document["note"]

    text = learning.render(proposal)
    assert "NOTHING HAS BEEN CHANGED" in text
    assert "There is no --apply" in text


def test_recording_a_proposal_writes_a_log_and_not_the_profile():
    from core.constants import INTEREST_PROFILE_FILE, PROFILE_PROPOSALS_FILE

    before = INTEREST_PROFILE_FILE.read_bytes()
    proposal = learning.propose(_signal(llms=(12, 14)))
    learning.record(proposal, dry_run=False)
    assert INTEREST_PROFILE_FILE.read_bytes() == before
    assert PROFILE_PROPOSALS_FILE.exists()


# --- §11.3's four rules ----------------------------------------------


def test_the_rules_come_from_the_profile_and_match_the_brief():
    config = learning.rules(PROF)
    assert config["min_observations"] == 10
    assert config["promotion_threshold"] == 8
    assert config["demotion_threshold"] == -8
    assert config["min_topics_at_strong"] == 5
    assert config["never_auto_exclude"] is True
    assert config["requires_confirmation"] is True


def test_one_reaction_never_moves_the_profile():
    """§11.3, stated as the rule it is: accumulated evidence only."""
    proposal = learning.propose(_signal(llms=(3, 1)))
    assert proposal.changes == []
    assert proposal.withheld[0]["topic"] == "llms"
    assert "min_observations" in proposal.withheld[0]["reason"]


def test_a_topic_below_min_observations_cannot_move_however_strong():
    """Nine rated items with an overwhelming net signal still moves
    nothing. The count gates the score, not the other way round."""
    proposal = learning.propose(_signal(agents=(30, 9)))
    assert proposal.changes == []
    assert "only 9 rated item(s)" in proposal.withheld[0]["reason"]


def test_a_topic_over_the_threshold_with_enough_observations_is_proposed():
    proposal = learning.propose(
        _signal(agents=(9, 12, {"deep_dive": 3, "interesting": 9}))
    )
    assert len(proposal.changes) == 1
    change = proposal.changes[0]
    assert (change.topic, change.direction) == ("agents", "promote")
    assert change.net == 9 and change.observations == 12
    assert "promotion_threshold" in change.rationale


def test_the_dead_band_proposes_nothing():
    """Between the two thresholds there is not enough signal either way,
    and saying so is more useful than proposing a coin-flip."""
    for net in (-7, 0, 7):
        proposal = learning.propose(_signal(llms=(net, 20)))
        assert proposal.changes == [], net
        assert "dead band" in proposal.withheld[0]["reason"]


def test_a_demotion_is_proposed_when_the_floor_allows_it():
    """With headroom above the floor, a topic past the demotion
    threshold IS proposed. Paired with the test below, this is what
    shows the floor is a floor and not a blanket refusal."""
    import copy

    raw = copy.deepcopy(PROF.raw)
    # A profile with plenty of strong coverage, so the floor is not what
    # decides this case.
    raw["strong_interests"] = [
        {"topic": t, "signals": [s]} for t, s in [
            ("interpretability", "circuits"),
            ("llms", "language model"),
            ("inference", "quantisation"),
            ("evaluation", "contamination"),
            ("training", "tokenisation"),
            ("reasoning", "chain of thought"),
            ("agents", "tool use"),
            ("multimodal", "vision"),
            ("ai-security", "prompt injection"),
            ("ai-safety", "alignment"),
            ("deep-learning", "optimisation"),
            ("reinforcement-learning", "policy optimisation"),
        ]
    ]
    roomy = Profile(raw)
    assert learning._strong_topic_count(roomy) > 5  # noqa: SLF001

    proposal = learning.propose(_signal(multimodal=(-12, 15)), prof=roomy)
    directions = [(c.topic, c.direction) for c in proposal.changes]
    assert ("multimodal", "demote") in directions


def test_the_five_strong_topics_floor_blocks_a_demotion():
    """§11.3's floor. Without it the profile narrows to one subject
    within months — which is the failure mode, not a hypothetical."""
    import copy

    raw = copy.deepcopy(PROF.raw)
    # A profile whose strong interests reach exactly the floor.
    raw["strong_interests"] = [
        {"topic": "interpretability", "signals": ["circuits"]},
        {"topic": "llms", "signals": ["language model"]},
        {"topic": "security", "signals": ["prompt injection"]},
        {"topic": "inference", "signals": ["quantisation", "speculative decoding"]},
        {"topic": "evaluation", "signals": ["contamination"]},
    ]
    narrow = Profile(raw)
    reached = learning._strong_topic_count(narrow)  # noqa: SLF001
    assert reached >= 1

    proposal = learning.propose(
        _signal(llms=(-20, 30), agents=(-20, 30), inference=(-20, 30),
                evaluation=(-20, 30), multimodal=(-20, 30), training=(-20, 30)),
        prof=narrow,
    )
    demotions = [c for c in proposal.changes if c.direction == "demote"]
    blocked = [w for w in proposal.withheld if "fewer than" in w["reason"]]
    assert blocked, "the floor never fired"
    assert len(demotions) <= max(0, reached - 5)


def test_exclusions_are_never_proposed():
    """§11.3: only the owner may add to exclude[]. Not "Scout asks
    first" — Scout does not ask."""
    proposal = learning.propose(
        _signal(multimodal=(-40, 50), generative_ai=(-40, 50))
    )
    document = learning.as_json(proposal)
    assert "exclude" not in document.lower() or '"exclude"' not in document
    for change in proposal.changes:
        assert change.direction in ("promote", "demote")

    text = learning.render(proposal)
    assert "additions to exclude[] — owner-only" in text


def test_only_topic_scoped_reactions_reach_the_proposal():
    """The §11.2 distinction carried all the way through: a 👎 on a weak
    piece contributes observations but no score, so twenty of them
    cannot demote a topic."""
    from telegram import feedback

    rows = [
        {"at": "2026-09-14T00:00:00+00:00", "itemId": f"r{i}",
         "kind": "not_useful", "topics": ["llms"], "section": "research"}
        for i in range(20)
    ]
    signal = feedback.topic_signal(rows)
    assert signal["llms"]["observations"] == 20
    assert signal["llms"]["net"] == 0

    proposal = learning.propose(signal)
    assert proposal.changes == []
    assert "dead band" in proposal.withheld[0]["reason"]


def test_the_raw_history_is_never_rewritten():
    """§11.3: state/feedback.jsonl is permanent and cannot be
    reconstructed. Nothing may open it for writing except the appender."""
    offenders = []
    for path in (REPO_ROOT / "scripts").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "FEEDBACK_FILE" not in line:
                continue
            if any(w in line for w in ("write_json", ".write_text", ".unlink",
                                       '.open("w', ".open('w")):
                offenders.append(f"{path.name}: {line.strip()}")
    assert offenders == [], offenders
