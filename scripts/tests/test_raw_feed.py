"""
The raw research feed (build brief §9, extended) — pure-function tests
only, matching test_papers.py's own discipline. No network, no Telegram.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from papers import rate  # noqa: E402
from papers import raw_feed  # noqa: E402


def _item(id="2609.00001", title="A paper", abstract="An abstract.", **kwargs):
    return {"id": id, "title": title, "abstract": abstract, **kwargs}


# --- rate.py: parsing and round-tripping the callback data -------------


def test_callback_data_round_trips_through_parse_callback():
    data = rate.callback_data(4, "2609.12345")
    assert rate.parse_callback(data) == (4, "2609.12345")


def test_parse_callback_rejects_anything_not_its_own_prefix():
    # feedback.py's own shape — must not be swallowed by this parser.
    assert rate.parse_callback("interesting:abc123") is None


def test_parse_callback_rejects_an_out_of_range_score():
    assert rate.parse_callback("rr:9:2609.12345") is None
    assert rate.parse_callback("rr:0:2609.12345") is None


def test_parse_callback_rejects_malformed_data():
    assert rate.parse_callback("") is None
    assert rate.parse_callback("rr:4") is None
    assert rate.parse_callback("rr:notanumber:2609.12345") is None


def test_unpack_message_recovers_title_and_bucket_and_score():
    text = "A paper about attention\n[llm · 3.5]\n\nSome abstract text.\n\narxiv.org/abs/2609.00001"
    title, bucket, score = rate._unpack_message(text)
    assert title == "A paper about attention"
    assert bucket == "llm"
    assert score == 3.5


def test_unpack_message_handles_an_unmatched_item():
    text = "An unmatched paper\n[unmatched]\n\nSome abstract text.\n\narxiv.org/abs/2609.00002"
    title, bucket, score = rate._unpack_message(text)
    assert title == "An unmatched paper"
    assert bucket is None
    assert score == 0.0


# --- raw_feed.py: scoring split and batch selection ---------------------


def test_score_all_splits_matched_from_unmatched():
    profile = {
        "buckets": {"llm": {"weight": 1.0, "keywords": ["large language model"]}},
        "exclude": [],
    }
    items = [
        _item(id="1", title="A large language model does X"),
        _item(id="2", title="Something about turtles"),
    ]
    matched, unmatched = raw_feed.score_all(items, profile)
    assert [i["id"] for i in matched] == ["1"]
    assert [i["id"] for i in unmatched] == ["2"]


def test_score_all_sorts_matched_by_score_descending():
    profile = {
        "buckets": {"llm": {"weight": 1.0, "keywords": ["reasoning", "agentic", "inference"]}},
        "exclude": [],
    }
    items = [
        _item(id="weak", title="A paper about reasoning"),
        _item(id="strong", title="A paper about reasoning, agentic inference"),
    ]
    matched, _ = raw_feed.score_all(items, profile)
    assert [i["id"] for i in matched] == ["strong", "weak"]


def test_select_batch_respects_both_caps():
    matched = [_item(id=f"m{i}") for i in range(20)]
    unmatched = [_item(id=f"u{i}") for i in range(20)]
    import random

    batch = raw_feed.select_batch(
        matched, unmatched, matched_cap=3, unmatched_sample=2, rng=random.Random(0)
    )
    ids = [i["id"] for i in batch]
    assert len([i for i in ids if i.startswith("m")]) == 3
    assert len([i for i in ids if i.startswith("u")]) == 2


def test_select_batch_never_crashes_on_a_short_unmatched_pool():
    matched = [_item(id="m1")]
    unmatched = [_item(id="u1")]
    import random

    batch = raw_feed.select_batch(matched, unmatched, matched_cap=10,
                                   unmatched_sample=10, rng=random.Random(0))
    assert len(batch) == 2


def test_render_includes_bucket_score_and_link():
    item = {**_item(), "bucket": "llm", "keyword_score": 2.0}
    text = raw_feed.render(item)
    assert "[llm · 2.0]" in text
    assert "arxiv.org/abs/2609.00001" in text


def test_render_marks_an_unmatched_item_plainly():
    item = {**_item(), "bucket": None, "keyword_score": 0.0}
    text = raw_feed.render(item)
    assert "[unmatched]" in text


def test_render_truncates_a_long_abstract_on_a_word_boundary():
    item = {**_item(abstract="word " * 200), "bucket": None, "keyword_score": 0.0}
    text = raw_feed.render(item)
    body = text.split("\n\n")[1]
    assert body.endswith("…")
    assert not body.endswith(" …")  # cut point is a space, not mid-word


def test_rating_keyboard_has_five_buttons_wired_to_the_right_id():
    keyboard = raw_feed.rating_keyboard("2609.00001")
    assert len(keyboard) == 1
    assert [b["text"] for b in keyboard[0]] == ["1", "2", "3", "4", "5"]
    assert keyboard[0][2]["callback_data"] == "rr:3:2609.00001"
