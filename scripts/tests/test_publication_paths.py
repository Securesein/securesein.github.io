"""
Phase 5's acceptance criterion: G1-G5 are enforced on EVERY publication
path, and a deliberately corrupted draft is rejected.

test_gates.py already tests each gate in isolation. This file tests the
thing that isolation cannot: that no publication path can reach a
written file without going through them. A gate nothing calls is not a
gate, and that failure is invisible to a per-gate unit test.

Nothing here touches the network, a model, or the real repository: the
drafting call and the source fetch are both replaced, every state write
goes to the throwaway directories run_tests.py sets up, and every
assertion is about a file NOT being written.
"""

from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import pipeline  # noqa: E402
from core.feeds import Item, Source  # noqa: E402
from core.ledger import Queue  # noqa: E402
from core.llm import LLM, OFFLINE  # noqa: E402
from core.profile import QualityScore, RelevanceScore  # noqa: E402
from core.radar import Radar  # noqa: E402
from run import Context  # noqa: E402
from test_ledger import _FakeLedger  # noqa: E402

# A real-shaped source: the numbers in it are the only numbers a draft
# written from it is allowed to state.
SOURCE_TEXT = (
    "Today we are introducing Aurora 2.1, our new reasoning model. "
    "Aurora 2.1 scores 74.2% on SWE-bench Verified in our own evaluation, "
    "up from 61.5% for Aurora 2.0. It has a 400,000 token context window "
    "and is available today in the API at $3 per million input tokens."
)

HONEST_BODY = (
    "OpenAI has shipped Aurora 2.1, a reasoning model. The company says it "
    "scores 74.2% on SWE-bench Verified, up from 61.5% for Aurora 2.0, and "
    "that the context window is 400,000 tokens. It is available in the API "
    "at $3 per million input tokens."
)

# One number changed: 74.2 -> 78.2. Everything else is identical, which
# is the point — this is what a rounding slip or a half-remembered
# figure actually looks like, not an obviously broken draft.
CORRUPTED_BODY = HONEST_BODY.replace("74.2%", "78.2%")


def _ctx(dry_run: bool = True) -> Context:
    ledger = _FakeLedger([], dry_run=dry_run)
    return Context(
        channel="research",
        dry_run=dry_run,
        llm=LLM(OFFLINE),
        ledger=ledger,
        queue=Queue(ledger),
        radar=Radar(dry_run=dry_run, directory=Path(tempfile.mkdtemp(prefix="radar-"))),
    )


def _candidate() -> pipeline.Candidate:
    item = Item(
        id="https://openai.com/aurora-2-1",
        title="Introducing Aurora 2.1",
        url="https://openai.com/aurora-2-1",
        summary=SOURCE_TEXT,
        published="2026-09-14T00:00:00+00:00",
        source=Source(name="OpenAI News", url="https://openai.com/news", vendor="openai"),
    )
    candidate = pipeline.Candidate(
        item=item, section="release", format="news", topics=["llms", "reasoning"]
    )
    candidate.quality = QualityScore(total=88.0, passed=True)
    candidate.relevance = RelevanceScore(total=71.0)
    candidate.why = "A primary-source reasoning-model release."
    return candidate


class _Patched:
    """Replaces the fetch and the drafting call for one publication,
    so the gates run against text this file controls."""

    def __init__(self, body: str, source_text: str = SOURCE_TEXT):
        self.body, self.source_text = body, source_text

    def __enter__(self):
        self._fetch = pipeline.fetch_article_text
        self._call = pipeline.draft_module.call_model
        pipeline.fetch_article_text = lambda url, limit: self.source_text
        pipeline.draft_module.call_model = lambda *a, **k: {
            "title": "OpenAI ships Aurora 2.1",
            "description": "A reasoning model, with the vendor's own numbers.",
            "topics": ["llms", "reasoning"],
            "body": self.body,
        }
        return self

    def __exit__(self, *exc):
        pipeline.fetch_article_text = self._fetch
        pipeline.draft_module.call_model = self._call


def _g3_always_passes(llm, draft_body, source_text):
    from core.verify import GateResult

    return GateResult("G3", True, "stubbed verifier")


class _G3Stub:
    """G3 needs a model. Stubbing it to PASS is deliberate: it makes the
    deterministic gates the only thing that can reject, so a rejection
    in these tests can only have come from G1 or G2."""

    def __enter__(self):
        self._g3 = pipeline.g3_verifier
        pipeline.g3_verifier = _g3_always_passes
        return self

    def __exit__(self, *exc):
        pipeline.g3_verifier = self._g3


# --- the headline result ---------------------------------------------


def test_a_deliberately_corrupted_number_is_rejected_by_g1():
    """Phase 5's acceptance criterion, end to end through the real
    publication path rather than against the gate function alone.

    One figure in an otherwise perfect draft is changed from 74.2% to
    78.2%. Nothing else differs. There is no human review step and no
    retry, so this is the whole defence."""
    with _Patched(CORRUPTED_BODY), _G3Stub():
        slug = pipeline.publish(_ctx(), _candidate(), channel="releases")
    assert slug is None, "a draft with an ungrounded number must not publish"


def test_the_same_draft_with_the_right_number_publishes():
    """The other half of the proof: the rejection above is caused by the
    corruption, not by the harness. Same path, same stubs, one digit."""
    with _Patched(HONEST_BODY), _G3Stub():
        slug = pipeline.publish(_ctx(), _candidate(), channel="releases")
    assert slug, "an honest draft must still publish"


def test_a_rejected_draft_writes_nothing_to_the_blog_directory():
    """The rejection has to happen BEFORE the file is written, not after.
    Run with dry_run=False so the write is genuinely reachable."""
    from core.constants import BLOG_DIR

    before = {p.name for p in BLOG_DIR.glob("*.md")}
    with _Patched(CORRUPTED_BODY), _G3Stub():
        pipeline.publish(_ctx(dry_run=False), _candidate(), channel="releases")
    assert {p.name for p in BLOG_DIR.glob("*.md")} == before


def test_a_rejected_draft_is_logged_with_the_gate_that_caught_it():
    """§10: every failure is written to rejected.jsonl WITH the gate id
    and the offending content, so a rejection can be understood months
    later without re-fetching the source."""
    from core.constants import REJECTED_FILE
    from core.state import read_jsonl

    with _Patched(CORRUPTED_BODY), _G3Stub():
        pipeline.publish(_ctx(), _candidate(), channel="releases")

    rows = [r for r in read_jsonl(REJECTED_FILE)
            if r.get("reason") == "gate_g1_ungrounded_number"]
    assert rows, "the G1 rejection was not logged"
    last = rows[-1]
    assert last["detail"]["gate"] == "G1"
    assert any("78.2" in str(x) for x in last["detail"]["offending"])


def test_a_post_about_something_the_source_never_names_is_rejected_by_g2():
    """G2, through the same path. The draft's numbers are all present in
    the source, so G1 passes and G2 is what stops it."""
    candidate = _candidate()
    release = {"vendor": "openai", "family": "gpt-astra", "version": "6",
               "eventType": "new_model"}
    with _Patched(HONEST_BODY), _G3Stub():
        slug = pipeline.publish(
            _ctx(), candidate, channel="releases", release=release
        )
    assert slug is None


# --- coverage: no path can skip the gates ----------------------------


def test_every_publication_path_runs_the_gates():
    """The check a per-gate unit test cannot make.

    There are exactly three places in this repository that write a post
    file, and each one must run the gates first. If a fourth appears,
    this fails.
    """
    from channels import benchmarks, releases

    writers = {
        "core/pipeline.publish": inspect.getsource(pipeline.publish),
        "channels/releases.publish_one": inspect.getsource(releases.publish_one),
        "channels/benchmarks._maybe_roundup": inspect.getsource(
            benchmarks._maybe_roundup  # noqa: SLF001
        ),
    }
    for name, source in writers.items():
        assert "write_post(" in source, f"{name} is not a publication path any more"
        ran_a_gate = any(
            marker in source
            for marker in ("run_gates(", "run_release_gates(", "g5_reference_integrity(")
        )
        assert ran_a_gate, f"{name} writes a post without running the gates"

    # And nothing else writes one.
    found = set()
    for path in (REPO_ROOT / "scripts").rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "write_post(" in text and "def write_post" not in text:
            found.add(path.relative_to(REPO_ROOT).as_posix())
    assert found == {
        "scripts/core/pipeline.py",
        "scripts/channels/releases.py",
        "scripts/channels/benchmarks.py",
        # The legacy Telegram marked-item path. It writes through its own
        # helper because its provenance differs (the owner asked for it
        # by name), but it runs pipeline.run_gates first — asserted
        # below — so it is not a fourth ungated path.
        "scripts/channels/research.py",
    }, f"an unexpected module writes posts: {found}"

    from channels import research

    marked = inspect.getsource(research.run_marked)
    assert "pipeline.run_gates(" in marked, (
        "the marked-item path writes posts without running the gates"
    )


def test_the_gates_run_in_cost_order():
    """G1 and G2 are free and G3 costs money, so a draft with an invented
    number must never reach the verifier. Asserted from the order the
    calls appear in, because an accidental reorder is silent and shows
    up only as a bill."""
    source = inspect.getsource(pipeline.run_gates)
    assert source.index("g1_numeric_grounding") < source.index("g2_entity_grounding")
    assert source.index("g2_entity_grounding") < source.index("g3_verifier")
    assert source.index("g5_reference_integrity") < source.index("g3_verifier")


def test_there_is_no_retry_and_no_override():
    """§10: "Do not retry with a different prompt." A gate you can
    re-roll is not a gate.

    Checked as structure rather than vocabulary: the gates are called
    exactly once each, from straight-line code with no loop around them
    and no second call site, and a failure returns rather than falling
    through to another attempt."""
    source = inspect.getsource(pipeline.run_gates)
    for gate in ("g1_numeric_grounding(", "g2_entity_grounding(",
                 "g3_verifier(", "g5_reference_integrity("):
        assert source.count(gate) == 1, f"{gate} is called more than once"
    assert "for " not in source.split("def run_gates")[1].split("return results")[0] \
        or "while " not in source, "the gate sequence must not loop"

    publish_source = inspect.getsource(pipeline.publish)
    assert publish_source.count("run_gates(") == 1
    # A gate failure returns. There is no branch that continues past it.
    assert "if failed is not None:" in publish_source
    assert "return None" in publish_source.split("if failed is not None:")[1]


def test_a_dry_run_still_runs_every_gate_for_real():
    """A dry run that skipped the gates would report "would publish" for
    a draft that would in fact have been rejected — which is worse than
    not running at all, because it looks like evidence."""
    with _Patched(CORRUPTED_BODY), _G3Stub():
        assert pipeline.publish(_ctx(dry_run=True), _candidate(), channel="releases") is None
    with _Patched(HONEST_BODY), _G3Stub():
        assert pipeline.publish(_ctx(dry_run=True), _candidate(), channel="releases")


def test_the_marked_item_path_is_gated_too():
    """The one live publication path, and the one most likely to be
    assumed safe because a human picked the article."""
    from channels import research

    source = inspect.getsource(research.run_marked)
    assert "pipeline.run_gates(" in source
    assert "GATE_REASONS" in source


def test_g3_fails_closed_with_no_verifier():
    """The asymmetry §10 asks for: the deterministic gates fail open in
    documented places because a missed post costs less than a stalled
    pipeline, but the gate whose whole job is catching invented claims
    must never wave a draft through because it could not run."""
    with _Patched(HONEST_BODY):  # no G3 stub: offline, so no verifier
        slug = pipeline.publish(_ctx(), _candidate(), channel="releases")
    assert slug is None


def test_a_source_too_short_to_ground_anything_publishes_nothing():
    """G1 against an empty source would either pass everything or fail
    everything. Neither is a gate, so the path refuses earlier."""
    with _Patched(HONEST_BODY, source_text="too short"), _G3Stub():
        assert pipeline.publish(_ctx(), _candidate(), channel="releases") is None
