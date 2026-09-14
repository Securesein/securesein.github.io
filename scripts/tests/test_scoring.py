"""
Two-stage scoring (brief §7.1), the exclusion filter, and the topic
starvation bonus.

The property that matters most here is the one a single weighted sum
cannot have: **relevance can never open the gate.** A maximally
relevant item that fails on quality stays out; a barely relevant one
that passes on quality gets in and ranks last. Several tests below exist
only to pin that down, because it is the rule most likely to be
"simplified" back into one number by a future edit.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import taxonomy as tax  # noqa: E402
from core.feeds import Item, Source  # noqa: E402
from core.profile import (  # noqa: E402
    TopicActivity,
    discovery_mix,
    excluded,
    profile as load_profile_object,
    quality_gate_offline,
    relevance_rank,
)

PROF = load_profile_object()


def _item(title, summary="", *, tier="primary", source="OpenAI News", days_old=0,
          url="https://example.com/a"):
    published = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return Item(
        id=url, title=title, url=url, summary=summary, published=published,
        source=Source(name=source, url=url, tier=tier),
    )


# --- the profile itself ----------------------------------------------


def test_profile_parses_and_survives_the_a2_reconciliation():
    """interest_profile.yaml had a YAML syntax error that made the whole
    file unparseable (an unquoted line starting with a quoted run). If
    that regresses, every exclusion silently stops firing."""
    assert PROF.quality_minimum == 55
    assert set(PROF.quality_weights) == {
        "technical_substance", "source_quality", "novelty", "verifiability",
    }
    assert sum(PROF.quality_weights.values()) == 100
    assert PROF.low_interest_penalty == -25


def test_five_topics_stay_strong_floor_holds():
    """§11.3's floor: at least five topics at `strong`. Checked against
    the file as committed, so a reconciliation that commented out too
    much would fail here rather than in production."""
    assert len(PROF.strong) >= 5


def test_retired_sections_and_topics_are_gone_from_the_vocabulary():
    """Decision A2, asserted against taxonomy.json itself."""
    assert "practice" not in tax.section_slugs()
    assert "fieldnote" not in tax.format_slugs()
    for slug in ("mobility", "enterprise", "selfhosted", "industry"):
        assert slug not in tax.topic_slugs(), slug
    assert len(tax.section_slugs()) == 5
    assert len(tax.format_slugs()) == 5
    assert len(tax.topic_slugs()) == 13


# --- the exclusion filter --------------------------------------------


def test_funding_and_acquisitions_are_excluded_before_scoring():
    """The first line of exclude[], and the reason
    nvidia-s-acquisition-of-hugging-face is in the archive as an
    EXCEPTION rather than as something the new pipeline would publish."""
    fired = excluded(
        "Nvidia confirms it will buy Hugging Face for $12.9 billion",
        "The acquisition values the platform at...", "TechCrunch AI", PROF,
    )
    assert fired and "acquisitions" in fired


def test_publisher_about_itself_is_excluded():
    fired = excluded(
        "VentureBeat names Rob Strechay as its first lead analyst",
        "", "VentureBeat AI", PROF,
    )
    assert fired == "publisher-about-itself stories"


def test_a_vendor_writing_about_its_own_product_is_not_excluded():
    """The exclusion must not fire on exactly what the site is for."""
    assert excluded(
        "Google's August AI announcements: a closer look at Gemini",
        "New models and capabilities.", "Google AI Blog", PROF,
    ) is None


def test_only_lines_present_in_the_profile_can_fire():
    """§11.3 makes exclude[] owner-only. A pattern this module knows
    about but the profile has dropped must stay silent, or the code
    would be enforcing an exclusion the owner removed."""
    import copy

    from core.profile import Profile

    raw = copy.deepcopy(PROF.raw)
    raw["exclude"] = ["conference and webinar announcements"]
    narrowed = Profile(raw)
    assert excluded("Acme raises $40M Series B", "", "TechCrunch AI", narrowed) is None
    assert excluded("Register now for our webinar", "", "TechCrunch AI", narrowed)


# --- stage 1: the quality gate ---------------------------------------


def test_a_bare_headline_fails_the_gate():
    score = quality_gate_offline(_item("Something happened"), PROF)
    assert not score.passed
    assert score.total < PROF.quality_minimum


def test_a_paper_with_a_mechanism_and_numbers_passes():
    score = quality_gate_offline(
        _item(
            "Speculative decoding with a learned drafter",
            "We show why the acceptance rate rises: the drafter's KV cache is "
            "reused across steps, giving 2.4x throughput at equal quality. Code "
            "is available on GitHub and the ablation is in the appendix. "
            "We measure results on four benchmarks and report the baseline.",
            source="arXiv cs.LG",
        ),
        PROF,
    )
    assert score.passed
    assert score.total >= PROF.quality_minimum


def test_source_tier_moves_the_gate_but_does_not_decide_it():
    """§8.1: tiering is enforced in code. A community source scores
    lower on the source_quality component and can still pass on
    substance, which is correct — the tier decides what may TRIGGER a
    release, not what is allowed to be good."""
    body = ("We show the mechanism: the residual stream carries the refusal "
            "direction, and ablating it raises compliance by 41%. Code on GitHub. "
            "We measure the result against a baseline in the appendix.")
    primary = quality_gate_offline(_item("A finding", body, tier="primary"), PROF)
    community = quality_gate_offline(_item("A finding", body, tier="community"), PROF)
    assert primary.total > community.total


def test_a_roundup_source_is_capped_on_source_quality():
    """§8.3: roundups are discovery aids. They are not banned from the
    gate — the channel rejects them outright before scoring — but a
    roundup must never score as a primary source."""
    body = "We show the mechanism and measure a 12% improvement. Code on GitHub."
    roundup = quality_gate_offline(
        _item("A finding", body, source="Import AI (Jack Clark)"), PROF
    )
    primary = quality_gate_offline(_item("A finding", body, source="OpenAI News"), PROF)
    assert roundup.total < primary.total


def test_novelty_decays_with_age():
    body = "We show the mechanism and measure a 12% improvement. Code on GitHub."
    fresh = quality_gate_offline(_item("A finding", body, days_old=0), PROF)
    stale = quality_gate_offline(_item("A finding", body, days_old=60), PROF)
    assert fresh.total > stale.total


# --- stage 2: relevance rank -----------------------------------------


def test_relevance_never_opens_the_gate():
    """THE load-bearing property of the whole design. An item stuffed
    with strong-interest signals but no substance still fails stage 1,
    and stage 2 is never consulted."""
    item = _item(
        "Prompt injection, residual stream, speculative decoding, sparse autoencoders",
        "",  # no body: nothing substantial to score
    )
    quality = quality_gate_offline(item, PROF)
    assert not quality.passed

    # If it HAD been ranked, it would have scored highly — which is
    # exactly why the two stages must not be added together.
    relevance = relevance_rank(item, "research", ["interpretability"], PROF)
    assert relevance.total > 40


def test_a_strong_interest_match_outranks_a_medium_one():
    strong = relevance_rank(
        _item("Activation steering in the residual stream",
              "We probe the refusal direction."),
        "research", ["interpretability"], PROF,
    )
    medium = relevance_rank(
        _item("A new video generation model", "Audio and video generation."),
        "research", ["multimodal"], PROF,
    )
    assert strong.total > medium.total
    assert strong.bucket == "strong"


def test_low_interest_carries_a_penalty():
    plain = relevance_rank(
        _item("A result", "Some finding."), "research", ["llms"], PROF
    )
    low = relevance_rank(
        _item("A result about robotics", "Some finding about robotics."),
        "research", ["llms"], PROF,
    )
    assert low.total < plain.total
    assert low.components["low_interest_penalty"] == PROF.low_interest_penalty


def test_depth_bonus_prefers_mechanism_over_event():
    """§8.3's "mechanism over event", made true in the ranking rather
    than only in the prose."""
    mechanism = relevance_rank(
        _item("How speculative decoding works",
              "The mechanism is that the drafter's tokens are verified in one pass."),
        "research", ["inference"], PROF,
    )
    event = relevance_rank(
        _item("Speculative decoding shipped", "It is now available."),
        "research", ["inference"], PROF,
    )
    assert mechanism.components["depth_bonus"] > event.components["depth_bonus"]


# --- topic starvation -------------------------------------------------


def _activity(**last) -> TopicActivity:
    activity = TopicActivity(PROF)
    activity.last = dict(last)
    return activity


def test_a_never_published_topic_is_maximally_starved():
    activity = _activity()
    assert activity.bonus(["generative-ai"]) == activity.max_bonus


def test_a_freshly_published_topic_gets_no_bonus():
    today = date.today().isoformat()
    activity = _activity(llms=today)
    assert activity.bonus(["llms"]) == 0.0


def test_the_bonus_is_capped_at_the_profile_maximum():
    long_ago = (date.today() - timedelta(days=400)).isoformat()
    activity = _activity(llms=long_ago)
    assert activity.bonus(["llms"]) == activity.max_bonus
    assert activity.max_bonus == 10


def test_starvation_reorders_but_cannot_admit():
    """It is a stage-2 term. Applied to a survivor it changes the
    order; there is no code path by which it reaches stage 1."""
    item = _item("A finding", "We show the mechanism and measure 12%.")
    plain = relevance_rank(item, "research", ["llms"], PROF, starvation_bonus=0)
    starved = relevance_rank(item, "research", ["llms"], PROF, starvation_bonus=10)
    assert starved.total == plain.total + 10

    import inspect

    from core import profile as profile_module

    gate_source = inspect.getsource(profile_module.quality_gate_offline)
    assert "starvation" not in gate_source


# --- discovery mix ----------------------------------------------------


def test_discovery_mix_is_reported_not_enforced():
    mix = discovery_mix(
        [{"bucket": "strong"}] * 7 + [{"bucket": "adjacent"}] * 2
        + [{"bucket": "serendipity"}]
    )
    assert mix["n"] == 10
    assert mix["shares"] == {"strong": 0.7, "adjacent": 0.2, "serendipity": 0.1}

    # Nothing in the ranking consults it — §7.1 says weekly, not
    # per-run, and a per-run quota would push weaker material through.
    import inspect

    from core import pipeline, profile as profile_module

    assert "discovery_mix" not in inspect.getsource(pipeline.run_flow)
    assert "discovery" not in inspect.getsource(profile_module.relevance_rank)
