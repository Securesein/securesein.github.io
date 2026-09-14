"""
The per-section rules of §8, as behaviour rather than as prose.

Every rule in §8 is a claim about what the pipeline will and will not
publish. A rule that lives only in a prompt is a rule the model follows
most of the time, and "most of the time" is the wrong number for a
system that publishes unreviewed — so the ones that matter are enforced
in code, and this file is where that is checked.

There is no Practice section and no `practice` channel: decision A2.
test_scoring.py asserts that against the vocabulary; here it is asserted
against the pipeline's own module list.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from channels import releases, research, security  # noqa: E402
from core import classify, taxonomy as tax  # noqa: E402
from core.constants import CHANNELS  # noqa: E402
from core.feeds import Item, Source  # noqa: E402


def _item(title, summary="", *, source="arXiv cs.LG", tier="primary"):
    return Item(
        id=title, title=title, url="https://example.com/a", summary=summary,
        published="2026-09-14T00:00:00+00:00",
        source=Source(name=source, url="https://example.com", tier=tier),
    )


# --- §8.3 Research ----------------------------------------------------


def test_a_roundup_only_source_can_never_trigger_a_research_post():
    """§8.3's hard rule. A HARD REJECT rather than a score penalty,
    because a penalty is something a quiet week overcomes — and the
    whole point is that the pipeline follows the roundup to the primary
    source or drops the item."""
    for name in ("Import AI (Jack Clark)", "TLDR AI",
                 "Hugging Face — Daily Papers", "KDnuggets"):
        assert research._roundup_only(_item("A paper", source=name)) == (  # noqa: SLF001
            "roundup_only_source"
        ), name
    assert research._roundup_only(_item("A paper", source="arXiv cs.LG")) is None  # noqa: SLF001


def test_the_same_rule_applies_to_security():
    assert security._not_post_worthy(  # noqa: SLF001
        _item("An attack", source="Import AI (Jack Clark)")
    ) == "roundup_only_source"


def test_research_section_rules_name_negative_results_as_first_class():
    """§8.3: replication failures, contamination findings and negative
    results are first-class Research material and routinely more useful
    than positive ones. The drafter is told so explicitly, because this
    is a rule about what to WRITE and cannot be enforced structurally."""
    rules = research.SECTION_RULES.lower()
    assert "negative result" in rules
    assert "replication failure" in rules
    assert "contamination" in rules
    assert "mechanism over event" in rules


def test_mechanism_outranks_event_in_the_ranking_not_only_in_the_prose():
    """The `depth_bonus` term exists so §8.3's "mechanism over event" is
    true of the QUEUE ORDER and not only of the house style. Covered in
    detail by test_scoring; asserted here as a section rule so that
    removing the term fails a §8 test too."""
    from core.profile import profile as load_profile_object, relevance_rank

    prof = load_profile_object()
    assert prof.relevance_weights["depth_bonus"] > 0
    mechanism = relevance_rank(
        _item("How it works", "The mechanism is that the cache is reused."),
        "research", ["inference"], prof,
    )
    assert mechanism.components["depth_bonus"] > 0


# --- §8.4 Security ----------------------------------------------------


def test_reward_hacking_is_security_not_research():
    """§8.4, stated as an override of the obvious reading: reward
    hacking and specification gaming arrive from ML venues and read like
    results, but they are failure modes."""
    for title in ("Reward hacking in RLHF-trained policies",
                  "Specification gaming: a new taxonomy",
                  "Spec gaming in agentic evaluations"):
        assert classify.deterministic_axes(_item(title))["section"] == "security", title


def test_a_defensive_tools_point_release_is_not_a_post():
    """§8.4: garak v0.x.y is not a Security post."""
    assert security._not_post_worthy(  # noqa: SLF001
        _item("v0.12.1", "Bug fixes and dependency bumps.",
              source="garak (NVIDIA) — LLM vulnerability scanner")
    ) == "no_product_angle"


def test_the_attack_class_a_defensive_tool_responds_to_is_a_post():
    """The other half of the same rule — a new probe family is."""
    assert security._not_post_worthy(  # noqa: SLF001
        _item("New probe family for indirect prompt injection via documents",
              "Adds probes covering a documented bypass of tool-call filtering.",
              source="garak (NVIDIA) — LLM vulnerability scanner")
    ) is None


def test_security_section_rules_require_a_practitioner_consequence():
    """§8.4: where a finding has a concrete enterprise consequence, say
    what a practitioner should actually do about it. Under A2 there is
    no Practice section for that to bridge to, so the advice has to live
    inside the Security post."""
    rules = security.SECTION_RULES.lower()
    assert "practitioner" in rules
    assert "attack class" in rules
    assert "reward hacking" in rules


# --- §8.1 Model Updates -----------------------------------------------


def test_only_a_primary_source_can_trigger_a_release():
    """§8.1, enforced via the `tier` field in code rather than asked of
    a prompt. Covered end to end in test_releases; asserted here as the
    section rule it is."""
    from core.feeds import TIER_COMMUNITY, TIER_CORROBORATING, TIER_PRIMARY

    assert Source(name="x", url="y", tier=TIER_PRIMARY).may_trigger
    assert not Source(name="x", url="y", tier=TIER_CORROBORATING).may_trigger
    assert not Source(name="x", url="y", tier=TIER_COMMUNITY).may_trigger


def test_a_runtime_release_is_not_a_model_release():
    """§8.1: "An Ollama point release is exactly what this section
    exists to suppress"."""
    registry_free = classify.RUNTIME_RELEASE
    for title in ("Ollama v0.5.2", "vLLM 0.6.3 release",
                  "llama.cpp b4200", "transformers v4.46.0"):
        assert registry_free.search(title), title


# --- §8.6 Fundamentals ------------------------------------------------


def test_fundamentals_is_never_classified_into_from_a_feed():
    """§8.6: Fundamentals is NOT driven by the feed pipeline — those are
    generated from the Radar and the benchmarks collection when a
    concept keeps recurring. A classifier that files a feed item there
    is wrong rather than interesting, so nothing can."""
    assert "explainer" not in [slug for slug, _ in classify.SECTION_PATTERNS]
    for title in ("What are diffusion models?", "A gentle introduction to attention",
                  "Explained: how tokenisation works"):
        assert classify.deterministic_axes(_item(title))["section"] != "explainer", title


# --- A2: no Practice --------------------------------------------------


def test_there_is_no_practice_channel_anywhere():
    assert "practice" not in CHANNELS
    assert not (REPO_ROOT / "scripts" / "channels" / "practice.py").exists()
    assert not (REPO_ROOT / "src" / "pages" / "practice").exists()
    assert "practice" not in tax.section_slugs()


def test_no_channel_module_treats_practice_as_a_section():
    """The word may appear in prose explaining why the section is gone;
    it must never appear as a value the code uses."""
    import ast

    for module in (releases, research, security):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A docstring is prose, not a value.
                if len(node.value) > 120:
                    continue
                assert node.value.strip().lower() != "practice", module.__name__
            if isinstance(node, ast.Name):
                assert node.id.lower() != "practice", module.__name__


# --- §9 budgets, as the sections actually see them --------------------


def test_every_section_has_a_budget_and_practice_has_none():
    """Decision A1's table: {release 6, research 6, security 4,
    benchmark 2, explainer 1} = 19/week, with the brief's `practice: 2`
    row removed along with the section. The shortfall against the
    brief's stated ~21 is expected, not a bug."""
    import json

    budgets = json.loads(
        (REPO_ROOT / "config" / "budgets.json").read_text(encoding="utf-8")
    )
    targets = budgets["targets_7d"]
    assert targets == {
        "release": 6, "research": 6, "security": 4, "benchmark": 2, "explainer": 1
    }
    assert sum(targets.values()) == 19
    assert set(targets) == set(tax.section_slugs())
    assert budgets["hard_cap_7d"] == 50
    assert "practice" not in targets
