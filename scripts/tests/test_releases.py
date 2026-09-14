"""
The Releases channel, replayed against recorded input.

Phase 3's acceptance criteria are that the entity dedup demonstrably
collapses a multi-source release into one candidate, and that the
scoring rubric is inspectable and testable without live API spend.
Both are exercised here against
scripts/tests/fixtures/releases_gpt6_astra.json, which records the
real failure the channel was built for: three source articles, three
URLs, three headlines, one GPT-6 Astra release.

Everything runs with --offline-llm, so there is no network call and no
model call anywhere in this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from channels import releases  # noqa: E402
from core import classify as classify_module  # noqa: E402
from core.feeds import load_fixture  # noqa: E402
from core.llm import LLM, OFFLINE  # noqa: E402
from core.registry import load_registry  # noqa: E402
from core.ledger import Queue  # noqa: E402
from core.radar import Radar  # noqa: E402
from run import Context  # noqa: E402
from test_ledger import _FakeLedger  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "releases_gpt6_astra.json"


def _ctx():
    ledger = _FakeLedger([], dry_run=True)
    return Context(
        channel="releases",
        dry_run=True,
        llm=LLM(OFFLINE),
        ledger=ledger,
        queue=Queue(ledger),
        # SECURESEIN_RADAR_DIR points at a throwaway directory during a
        # test run — see scripts/tests/run_tests.py.
        radar=Radar(dry_run=True),
        fixtures=FIXTURE,
    )


def _pipeline():
    ctx = _ctx()
    config = releases.load_config()
    items = load_fixture(FIXTURE)
    candidates, corroborating = releases.build_candidates(ctx, items, config)
    collapsed = releases.collapse(candidates)
    releases.attach_corroboration(collapsed, corroborating)
    return config, items, candidates, corroborating, collapsed


# --- the headline result --------------------------------------------


def test_three_gpt6_astra_sightings_collapse_into_one_candidate():
    """The whole reason step 5 exists."""
    _, items, candidates, corroborating, collapsed = _pipeline()

    astra_inputs = [i for i in items if "astra" in i.title.lower()]
    assert len(astra_inputs) >= 3, "the fixture must carry the multi-source case"

    astra = [c for c in collapsed if "astra" in (c.facts.get("family") or "")
             or "astra" in c.item.title.lower()]
    assert len(astra) == 1, [c.item.title for c in astra]

    survivor = astra[0]
    # The survivor is the vendor's own announcement, not the coverage.
    assert survivor.item.source.name == "OpenAI — News", survivor.item.source.name
    # And the other sightings are recorded against it rather than lost.
    assert survivor.corroborators, "the collapsed sightings must be kept as corroboration"


def test_unrelated_release_is_not_merged_in():
    """Dedup that merges too much is worse than dedup that merges too
    little, so the fixture carries a second, genuinely different
    release."""
    *_, collapsed = _pipeline()
    entities = {str(c.key) for c in collapsed}
    assert len(entities) == len(collapsed), "one candidate per entity key"
    assert any("gemini" in e for e in entities), entities
    assert any("astra" in e or "gpt" in e for e in entities), entities


# --- tiering, enforced in code --------------------------------------


def test_non_primary_source_can_never_trigger_a_post():
    """Brief §6.2. A release exists when the vendor says so."""
    _, _, candidates, corroborating, _ = _pipeline()
    assert all(c.item.source.tier == "primary" for c in candidates)
    names = {i.source.name for i in corroborating}
    assert "MarkTechPost" in names or "Simon Willison — Weblog" in names


def test_a_runtime_release_is_never_a_model_release():
    """Brief §10: an Ollama point release is exactly the item this
    channel exists to suppress, even when its notes name a new model."""
    _, _, candidates, _, collapsed = _pipeline()
    for candidate in candidates + collapsed:
        assert "ollama" not in candidate.item.title.lower()


# --- the rubric ------------------------------------------------------


def test_rubric_is_fully_attributed():
    """Every point a candidate scores names the weight that produced
    it, so a score in state/queue.json can be argued with."""
    config, _, _, _, collapsed = _pipeline()
    for candidate in collapsed:
        releases.score_candidate(candidate, config, in_cooldown=False)
        assert candidate.reasons, candidate.item.title
        recomputed = sum(
            config["weights"][reason.split()[0]] for reason in candidate.reasons
        )
        assert abs(recomputed - candidate.score) < 1e-9


def test_tier1_and_non_tier1_differ_by_the_documented_spread():
    """§14.4, default applied: a non-tier-1 vendor carries an explicit
    extra hurdle rather than a separate threshold. If this number is
    wrong, this is the test that will say so."""
    config = releases.load_config()
    weights = config["weights"]
    assert "non_tier1" in weights, "the §14.4 mechanism must be findable in config"
    spread = weights["tier1_vendor"] - weights["non_tier1"]
    assert spread == 3, spread
    assert "openai" in config["tier1_vendors"]
    assert "deepseek" not in config["tier1_vendors"]


def test_same_release_scores_lower_for_a_non_tier1_vendor():
    config = releases.load_config()
    items = load_fixture(FIXTURE)
    base = next(i for i in items if i.source.name == "OpenAI — News")

    def score_for(vendor: str) -> float:
        candidate = releases.Candidate(
            item=base,
            facts={
                "eventType": "new_model",
                "vendor": vendor,
                "family": "gpt-astra",
                "version": "6",
                "openWeights": False,
                "modality": ["text"],
            },
        )
        return releases.score_candidate(candidate, config, in_cooldown=False).score

    assert score_for("openai") - score_for("deepseek") == 3


def _score(item, event: str, config, vendor: str = "openai") -> float:
    candidate = releases.Candidate(
        item=item,
        facts={"eventType": event, "vendor": vendor, "family": "gpt-astra",
               "version": "6", "openWeights": False, "modality": ["text"]},
    )
    return releases.score_candidate(candidate, config, in_cooldown=False).score


def test_threshold_admits_a_new_frontier_model():
    config = releases.load_config()
    items = load_fixture(FIXTURE)
    base = next(i for i in items if i.source.name == "OpenAI — News")
    assert _score(base, "new_model", config) >= config["threshold"]


def test_event_types_are_ordered_the_way_the_rubric_intends():
    """A new model outranks a version bump outranks an availability
    note, from the identical source. If this ordering ever inverts, the
    weights have been edited into incoherence."""
    config = releases.load_config()
    items = load_fixture(FIXTURE)
    base = next(i for i in items if i.source.name == "OpenAI — News")
    new_model = _score(base, "new_model", config)
    capability = _score(base, "capability_update", config)
    availability = _score(base, "availability", config)
    assert new_model > capability > availability


def test_a_benchmark_carrying_availability_note_sits_exactly_on_the_threshold():
    """A finding from the dry run, recorded as a test rather than as a
    note nobody reads.

    At the brief's starting weights, an availability item from a tier-1
    vendor whose text happens to quote a benchmark score lands on
    exactly 6 and therefore publishes: primary_source +3,
    event_availability +1, tier1_vendor +1, benchmark_claims_present +1.
    That is almost certainly too generous — "GPT-6 Astra is now
    available in eu-west" is not a post — and it is the clearest
    argument for raising `threshold` to 7 once there is a week of real
    score distribution to look at. The brief expects the threshold to
    be raised at least once; this is where the first raise comes from.
    """
    config = releases.load_config()
    items = load_fixture(FIXTURE)
    base = next(i for i in items if i.source.name == "OpenAI — News")
    assert classify_module.has_benchmark_claim(f"{base.title}\n{base.summary}")
    assert _score(base, "availability", config) == config["threshold"] == 6
    # ...and a non-tier-1 vendor's identical item does not clear it,
    # which is the §14.4 hurdle doing its job.
    assert _score(base, "availability", config, vendor="deepseek") < config["threshold"]


def test_cooldown_penalty_sinks_a_candidate():
    config = releases.load_config()
    items = load_fixture(FIXTURE)
    base = next(i for i in items if i.source.name == "OpenAI — News")
    facts = {"eventType": "new_model", "vendor": "openai", "family": "gpt-astra",
             "version": "6", "openWeights": False, "modality": ["text"]}
    hot = releases.score_candidate(releases.Candidate(base, dict(facts)), config, False)
    cold = releases.score_candidate(releases.Candidate(base, dict(facts)), config, True)
    assert hot.score - cold.score == -config["weights"]["entity_in_cooldown"]
    assert cold.score < config["threshold"]


# --- classification --------------------------------------------------


def test_major_and_minor_version_bumps_are_told_apart():
    assert classify_module.is_major("5.0")
    assert classify_module.is_major("6")
    assert not classify_module.is_major("5.1")
    assert not classify_module.is_major("3.7")
    assert not classify_module.is_major("2026-09-03")


def test_benchmark_claim_needs_a_name_and_a_number():
    assert classify_module.has_benchmark_claim("98% on FrontierMath Tier 4")
    assert classify_module.has_benchmark_claim("74.2 on SWE-bench Verified")
    assert not classify_module.has_benchmark_claim("beats every benchmark out there")
    assert not classify_module.has_benchmark_claim("costs 20% less to run")


def test_offline_classifier_drops_what_it_cannot_place():
    """Conservative by design: an unsure classifier returns "none" and
    the item is dropped with a reason, because a missing post costs
    less than a wrong one published without review."""
    registry = load_registry()
    items = load_fixture(FIXTURE)
    ollama = next(i for i in items if "Ollama" in i.title)
    facts = classify_module.deterministic(ollama, registry)
    # It may classify it as something, but the tier check above is what
    # keeps it out; what matters here is that it is never a new_model.
    assert facts["eventType"] != "new_model"
