"""
Reader Phase 1 (build brief §9). Pure-function tests only — no network,
matching the RSS fetch itself is deliberately untested here (it's a
single requests.get + feedparser.parse, and §9.1's asymmetry means a
failed fetch should just mean a quiet digest, not a red test suite).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from papers import run as papers  # noqa: E402


def _item(id="2609.00001", title="A paper", abstract="An abstract.",
          announce_type="new", **kwargs):
    return {
        "id": id, "title": title, "abstract": abstract,
        "link": f"https://arxiv.org/abs/{id}", "announce_type": announce_type,
        **kwargs,
    }


def test_dedup_keeps_first_occurrence_of_a_cross_listed_id():
    items = [_item(id="1", title="first"), _item(id="2"), _item(id="1", title="second")]
    out = papers.dedup(items)
    assert [i["id"] for i in out] == ["1", "2"]
    assert out[0]["title"] == "first"


def test_replace_and_replace_cross_are_dropped_new_and_cross_survive():
    items = [
        _item(id="1", announce_type="new"),
        _item(id="2", announce_type="cross"),
        _item(id="3", announce_type="replace"),
        _item(id="4", announce_type="replace-cross"),
    ]
    out = papers.drop_non_new(items)
    assert {i["id"] for i in out} == {"1", "2"}


def test_keyword_score_picks_the_highest_scoring_bucket():
    profile = {
        "buckets": {
            "llm": {"weight": 1.0, "keywords": ["large language model", "LLM"]},
            "rl": {"weight": 1.0, "keywords": ["reinforcement learning"]},
        },
        "exclude": [],
    }
    item = _item(title="A new LLM for large language model reasoning",
                 abstract="We study reinforcement learning too.")
    score, bucket = papers.keyword_score(item, profile)
    assert bucket == "llm"
    assert score > 0


def test_penalize_downweights_but_never_zeroes_a_medical_flavored_hit():
    profile = {
        "buckets": {"llm": {"weight": 1.0, "keywords": ["large language model"]}},
        "exclude": [],
        "penalize": {"factor": 0.35, "keywords": ["clinical"]},
    }
    plain = _item(title="A large language model for reasoning", abstract="...")
    clinical = _item(title="A large language model for clinical diagnosis", abstract="...")

    plain_score, plain_bucket = papers.keyword_score(plain, profile)
    clinical_score, clinical_bucket = papers.keyword_score(clinical, profile)

    assert clinical_bucket == "llm"  # still surfaces, unlike `exclude`
    assert 0 < clinical_score < plain_score


def test_an_excluded_phrase_zeroes_the_score_regardless_of_keyword_hits():
    profile = {
        "buckets": {"llm": {"weight": 1.0, "keywords": ["large language model"]}},
        "exclude": ["stochastic differential equation"],
    }
    item = _item(
        title="A large language model view of stochastic differential equations",
        abstract="...",
    )
    score, bucket = papers.keyword_score(item, profile)
    assert score == 0.0
    assert bucket is None


def test_prefilter_respects_the_survivor_cap_and_keeps_the_highest_scorers():
    profile = {
        "buckets": {"llm": {"weight": 1.0, "keywords": ["llm", "language model", "agent",
                                                          "reasoning", "inference"]}},
        "exclude": [],
    }
    # Ten candidates with an increasing number of keyword hits.
    items = [
        _item(id=str(i), title="llm " * i, abstract="language model agent reasoning inference"[: i * 3])
        for i in range(1, 11)
    ]
    out = papers.keyword_prefilter(items, profile, cap=3)
    assert len(out) == 3
    scores = [o["keyword_score"] for o in out]
    assert scores == sorted(scores, reverse=True)


def test_rank_and_cap_takes_the_top_n_by_score():
    scored = [{"id": str(i), "score": s} for i, s in enumerate([50, 90, 10, 70, 30])]
    out = papers.rank_and_cap(scored, cap=2)
    assert [o["score"] for o in out] == [90, 70]


def test_render_is_readable_with_zero_picks():
    text = papers.render([], total_new=42)
    assert "42" in text
    assert "arxiv.org" not in text  # no picks -> no links to dangle


def test_render_lists_bucket_counts_and_every_pick():
    picks = [
        {"id": "1", "title": "Paper one", "bucket": "llm", "one_line": "Claims X."},
        {"id": "2", "title": "Paper two", "bucket": "rl", "one_line": "Claims Y."},
    ]
    text = papers.render(picks, total_new=100)
    assert "2 of 100 new" in text
    assert "LLM 1" in text and "RL 1" in text
    assert "arxiv.org/abs/1" in text and "arxiv.org/abs/2" in text
    assert "Claims X." in text and "Claims Y." in text


def test_triage_drops_a_model_named_id_that_was_never_sent():
    """A triage response can't be trusted to only name real ids -- an
    unrecognised one is dropped, never guessed at (same discipline as
    Scout's classify.classify_axes for invented topics)."""
    from core.llm import LLM, OFFLINE

    llm = LLM(OFFLINE)
    batch = [
        {**_item(id="real-1"), "keyword_score": 3.0, "bucket": "llm"},
    ]

    def fake_json(*args, **kwargs):
        return {"papers": [
            {"id": "real-1", "bucket": "llm", "score": 80, "one_line": "ok"},
            {"id": "hallucinated-id", "bucket": "llm", "score": 99, "one_line": "no"},
        ]}

    llm.json = fake_json  # monkeypatch: exercise triage_batch's own filtering
    out = papers.triage_batch(llm, batch)
    assert [o["id"] for o in out] == ["real-1"]


def test_triage_stops_at_the_per_run_call_budget():
    from core.llm import LLM, OFFLINE

    llm = LLM(OFFLINE)
    survivors = [
        {**_item(id=str(i)), "keyword_score": 1.0, "bucket": "llm"}
        for i in range(papers.TRIAGE_BATCH_SIZE * 5)  # would be 5 batches uncapped
    ]
    out = papers.triage(llm, survivors, max_calls=2)
    # Offline stub always returns one row per input paper, so the call
    # count is what's actually under test here.
    assert len(out) == papers.TRIAGE_BATCH_SIZE * 2
