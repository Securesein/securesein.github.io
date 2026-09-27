"""
The benchmarks channel could not publish at all, and nothing said so.

render() always writes credit "scout". The schema demanded a `source`
on every Scout post. The benchmarks channel has no single source — a
roundup is written from the measurement collection, not from one
article — so it passed `benchmarkRefs` and no source. Every run from
2026-09-22 wrote its post, failed the build on that rule, and
discarded the run. Six days of a channel doing nothing, with its
workflow going red where nobody was looking.

The schema now accepts refs as provenance in place of a source. This
test guards the shape the channel actually emits, so the two cannot
drift apart again: it reads the real render() output rather than a
hand-written approximation of it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

CONFIG = REPO_ROOT / "src" / "content.config.ts"


def test_the_schema_accepts_refs_in_place_of_a_source():
    """Asserted against the schema text because the rule lives in
    TypeScript and this suite is Python. Crude, but it fails loudly if
    someone tightens the rule back without noticing what depends on
    it."""
    source = CONFIG.read_text(encoding="utf-8")
    rule = source[source.index("Existing rules, unchanged"):]
    rule = rule[: rule.index(".refine((d) => d.credit === \"scout\"")]

    assert "d.benchmarkRefs.length > 0" in rule, (
        "the Scout-provenance rule no longer accepts benchmarkRefs — the "
        "benchmarks channel emits exactly that and will fail the build"
    )
    assert "d.source !== undefined" in rule, "a source must still satisfy the rule"


def test_render_still_emits_scout_without_a_source_for_benchmarks():
    """If render() ever started emitting a source for benchmark posts,
    the schema change above would be dead weight — and if it stopped
    emitting refs, the posts would fail again."""
    from core import frontmatter

    body = (REPO_ROOT / "scripts" / "core" / "frontmatter.py").read_text(encoding="utf-8")
    assert 'credit: "scout"' in body, "render() no longer hardcodes the scout credit"

    channel = (REPO_ROOT / "scripts" / "channels" / "benchmarks.py").read_text(encoding="utf-8")
    call = channel[channel.index("text = render("):]
    call = call[: call.index(")")]
    assert "benchmark_refs=refs" in call, "the roundup no longer carries its refs"
    assert "source_url" not in call, (
        "the roundup now passes a source — if that is deliberate the schema "
        "rule and this test should be revisited together"
    )
