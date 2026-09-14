"""
The verification gates — the thing that replaces human review.

Phase 5's stated acceptance criterion is that the gates are enforced on
every publication path and that a deliberately corrupted draft, with an
altered number, is rejected by G1. That is
test_g1_rejects_a_deliberately_corrupted_number below, and it corrupts
a real draft built from a real source rather than a toy string.

Nothing here publishes anything, and nothing here calls a model: G3 is
driven by a stub LLM returning the four verdict shapes that matter.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.registry import load_registry  # noqa: E402
from core.verify import (  # noqa: E402
    g1_numeric_grounding,
    g2_entity_grounding,
    g2_models_resolve,
    g3_verifier,
    g5_reference_integrity,
    numbers_in,
)

# A real vendor announcement, and a draft honestly written from it.
SOURCE = (
    "Introducing GPT-6 Astra. GPT-6 Astra is available today in the API with a "
    "1.05 million token context window. OpenAI says Astra scores 98% on "
    "FrontierMath Tier 4 and completes professional tasks with 47% less time "
    "per task than GPT-5.6 Sol. Pricing starts at $1.25 per million input "
    "tokens. Weights are not released."
)

HONEST_DRAFT = (
    "OpenAI has shipped GPT-6 Astra, available in the API from today. The "
    "context window goes to 1.05 million tokens, and pricing starts at $1.25 "
    "per million input tokens; the weights are not released, so the API is the "
    "only way to run it. OpenAI says Astra scores 98% on FrontierMath Tier 4 "
    "and finishes professional tasks 47% faster than GPT-5.6 Sol — both vendor "
    "claims, not independent measurements."
)

RELEASE = {
    "vendor": "openai",
    "family": "gpt-astra",
    "version": "6",
    "eventType": "new_model",
    "modelHint": "GPT-6 Astra",
}


class _StubLLM:
    """Returns whatever verdict the test wants, without a network."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.offline = False

    def json(self, *args, **kwargs):
        return self.verdict


# --- G1 ---------------------------------------------------------------


def test_g1_passes_an_honest_draft():
    result = g1_numeric_grounding(HONEST_DRAFT, SOURCE)
    assert result.passed, result.offending


def test_g1_rejects_a_deliberately_corrupted_number():
    """THE Phase 5 acceptance criterion.

    One digit changed — 98% becomes 99% — in an otherwise perfect
    draft. This is the shape the failure actually takes: not a wild
    hallucination, a plausible rounding that no reader would question.
    """
    corrupted = HONEST_DRAFT.replace("98% on FrontierMath", "99% on FrontierMath")
    result = g1_numeric_grounding(corrupted, SOURCE)
    assert not result.passed
    assert result.gate == "G1"
    assert any("99" in offence for offence in result.offending), result.offending


def test_g1_rejects_an_invented_figure_outright():
    invented = HONEST_DRAFT + " It also scores 74.2% on SWE-bench Verified."
    result = g1_numeric_grounding(invented, SOURCE)
    assert not result.passed
    assert any("74.2" in offence for offence in result.offending)


def test_g1_normalises_the_forms_the_brief_lists():
    """Thousands separators, %, $, unit spacing, and 1.5k <-> 1500."""
    source = "The context window is 1,050,000 tokens. Latency fell 12.5%. It costs $1.25."
    assert g1_numeric_grounding("A 1.05M token window.", source).passed
    assert g1_numeric_grounding("1050000 tokens.", source).passed
    assert g1_numeric_grounding("Latency fell 12.5 %.", source).passed
    assert g1_numeric_grounding("It costs $ 1.25.", source).passed
    assert g1_numeric_grounding("A 1.5k window.", "A 1500 token window.").passed
    # ...and a genuinely different number still fails.
    assert not g1_numeric_grounding("A 2.05M token window.", source).passed


def test_g1_does_not_trip_over_a_version_number():
    """"Claude Opus 4.5" is an entity, not a claim about the world. G2
    checks it against the source; if G1 read its digits as a figure,
    every correct draft would be rejected."""
    source = "Anthropic released Claude Opus 4.5 today."
    assert g1_numeric_grounding("Anthropic shipped Claude Opus 4.5.", source).passed


def test_number_extraction_is_symmetric():
    assert 1_050_000.0 in numbers_in("a 1.05M context window")
    assert 1_050_000.0 in numbers_in("1,050,000 tokens")
    assert 98.0 in numbers_in("98%")
    assert 0.98 in numbers_in("98%")


# --- G2 ---------------------------------------------------------------


def test_g2_passes_when_the_source_names_the_subject():
    result = g2_entity_grounding(RELEASE, SOURCE, load_registry())
    assert result.passed, result.offending


def test_g2_rejects_a_post_about_something_the_source_never_mentions():
    """A model writing about what it expected to find rather than about
    what the source says."""
    other_source = "Anthropic released Claude Opus 4.8 today, with a longer context."
    result = g2_entity_grounding(RELEASE, other_source, load_registry())
    assert not result.passed
    assert result.gate == "G2"


def test_g2_rejects_a_wrong_version():
    wrong = {**RELEASE, "version": "7"}
    result = g2_entity_grounding(wrong, SOURCE, load_registry())
    assert not result.passed
    assert any("version" in offence for offence in result.offending)


def test_g2_roundup_half_requires_every_model_to_resolve():
    registry = load_registry()
    assert g2_models_resolve(["gpt-6-astra", "claude-opus-4-8"], registry).passed
    bad = g2_models_resolve(["gpt-6-astra", "Totally-Made-Up-Model"], registry)
    assert not bad.passed
    assert bad.offending == ["Totally-Made-Up-Model"]


# --- G3 ---------------------------------------------------------------


PASS_VERDICT = {
    "every_claim_in_source": True,
    "invented_claims": [],
    "version_matches_source": True,
    "vendor_claims_attributed": True,
    "verdict": "pass",
}


def test_g3_passes_on_a_clean_verdict():
    assert g3_verifier(_StubLLM(PASS_VERDICT), HONEST_DRAFT, SOURCE).passed


def test_g3_rejects_any_false():
    for key in ("every_claim_in_source", "version_matches_source", "vendor_claims_attributed"):
        verdict = {**PASS_VERDICT, key: False, "verdict": "fail"}
        result = g3_verifier(_StubLLM(verdict), HONEST_DRAFT, SOURCE)
        assert not result.passed, key
        assert key in result.detail


def test_g3_rejects_any_invented_claim_even_with_a_pass_verdict():
    """A verifier that says "pass" and then lists an invented claim is
    contradicting itself; the list wins."""
    verdict = {**PASS_VERDICT, "invented_claims": ["the 128k context window"]}
    result = g3_verifier(_StubLLM(verdict), HONEST_DRAFT, SOURCE)
    assert not result.passed
    assert result.offending == ["the 128k context window"]


def test_g3_rejects_unparseable_output_rather_than_retrying():
    for garbage in (None, "not json", [], {"unexpected": "shape"}):
        assert not g3_verifier(_StubLLM(garbage), HONEST_DRAFT, SOURCE).passed


def test_g3_fails_closed_when_no_verifier_is_available():
    """The one gate that must never wave a draft through because it
    could not run. With --offline-llm there is no verifier, so nothing
    publishes — which is the correct asymmetry against the gates that
    deliberately fail open."""
    from core.llm import LLM, OFFLINE

    assert not g3_verifier(LLM(OFFLINE), HONEST_DRAFT, SOURCE).passed


# --- G5 ---------------------------------------------------------------


KNOWN = {"gpqa-diamond--gpt-6-astra--epoch-ai--2026-08-30--abcd",
         "frontiermath--gpt-6-astra--openai--2026-09-05--8273"}
VALUES = {
    "gpqa-diamond--gpt-6-astra--epoch-ai--2026-08-30--abcd": 95.77,
    "frontiermath--gpt-6-astra--openai--2026-09-05--8273": 98.0,
}


def test_g5_passes_when_every_number_traces_to_a_cited_measurement():
    body = (
        "Epoch AI measured GPT-6 Astra at 95.77% on GPQA Diamond. OpenAI's own "
        "claim for FrontierMath Tier 4 is 98%."
    )
    result = g5_reference_integrity(body, sorted(KNOWN), KNOWN, VALUES)
    assert result.passed, result.offending


def test_g5_rejects_a_dangling_reference():
    result = g5_reference_integrity(
        "Nothing much.", ["a-measurement-that-does-not-exist"], KNOWN, VALUES
    )
    assert not result.passed
    assert result.offending == ["a-measurement-that-does-not-exist"]


def test_g5_rejects_a_number_that_traces_to_nothing():
    """The half that makes a roundup honest: a figure may not reach a
    reader unless it is also a record someone can check."""
    body = "Epoch AI measured GPT-6 Astra at 95.77% on GPQA and 61.4% on OSWorld."
    result = g5_reference_integrity(body, sorted(KNOWN), KNOWN, VALUES)
    assert not result.passed
    assert any("61.4" in offence for offence in result.offending)


def test_g5_rejects_a_roundup_that_cites_nothing():
    assert not g5_reference_integrity("Some prose.", [], KNOWN, VALUES).passed


# --- the sequence -----------------------------------------------------


def test_gates_run_in_cost_order_and_stop_at_the_first_failure():
    """The free deterministic checks run before the paid one, and a
    draft that fails G1 never reaches the model."""
    from core.verify import run_release_gates

    class _Counting(_StubLLM):
        def __init__(self):
            super().__init__(PASS_VERDICT)
            self.calls = 0

        def json(self, *args, **kwargs):
            self.calls += 1
            return self.verdict

    registry = load_registry()
    llm = _Counting()

    corrupted = {"body": HONEST_DRAFT.replace("98%", "99%")}
    results = run_release_gates(llm, corrupted, RELEASE, SOURCE, registry)
    assert [r.gate for r in results] == ["G1"]
    assert llm.calls == 0, "a draft that fails G1 must not reach the verifier"

    clean = {"body": HONEST_DRAFT}
    results = run_release_gates(llm, clean, RELEASE, SOURCE, registry)
    assert [r.gate for r in results] == ["G1", "G2", "G3"]
    assert all(r.passed for r in results)
    assert llm.calls == 1


def test_every_gate_failure_maps_to_a_logged_reason():
    """Each gate has its own rejection reason, so state/rejected.jsonl
    can be counted by gate in the weekly report."""
    from channels.releases import GATE_REASONS
    from core.state import QUALITY_REASONS

    assert set(GATE_REASONS) == {"G1", "G2", "G3", "G5"}
    assert set(GATE_REASONS.values()) <= QUALITY_REASONS
