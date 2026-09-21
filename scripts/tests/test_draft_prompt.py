"""
Regression test for the incident fixed 2026-09-21: a draft for the
hierarchical-memory-architecture paper couldn't find two worked
examples in its (pharmacology) source, so it invented a smart-grid
scenario and a financial-modeling failure mode that appear nowhere in
the source — the LENGTH & EXAMPLES requirement was pushing toward
fabrication with nothing telling the model a worked example has to
stay grounded in the source's own subject matter. See the post's own
"How this was made" note and build_system_prompt()'s new paragraph.

This only locks in that the constraint text survives future edits —
it can't verify a live model actually obeys it, the way G1's numeric
check can verify a number mechanically. The prompt is the whole fix
here; there is no deterministic gate for "is this example about the
same subject as the source," which is worth remembering if this ever
needs strengthening further.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import draft  # noqa: E402


def test_system_prompt_forbids_inventing_an_unrelated_example_domain():
    prompt = draft.build_system_prompt([], section="research")
    lowered = prompt.lower()
    assert "own subject matter" in lowered or "unrelated field" in lowered
    assert "smart-grid" in lowered, (
        "the concrete incident example should stay in the prompt — an "
        "abstract rule alone was tried implicitly (the old prompt already "
        "said 'from the source text') and a concrete counter-example is "
        "what was actually missing"
    )


def test_system_prompt_still_requires_real_worked_examples():
    """The fix must not have quietly softened the length/example bar
    while adding the grounding constraint."""
    prompt = draft.build_system_prompt([], section="research")
    assert "900 words" in prompt
    assert "worked example" in prompt.lower()
