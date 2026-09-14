"""
The Radar (brief §6) and its lifecycle.

Decision A3 made the Radar internal-only, which means nothing on the
public site will ever reveal a bug in it. These tests are the only thing
standing between a broken Radar and a digest that quietly stops
mentioning two thirds of what the pipeline looked at.

Every test here writes into the throwaway directory
SECURESEIN_RADAR_DIR points at — see scripts/tests/run_tests.py.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.radar import Radar, month_key, radar_id  # noqa: E402


def _radar() -> Radar:
    return Radar(dry_run=True, directory=Path(tempfile.mkdtemp(prefix="radar-test-")))


def _add(radar, **kwargs):
    defaults = dict(
        url="https://example.com/a", title="A finding", source="arXiv cs.LG",
        section="research", topics=["llms"], quality=80.0, relevance=60.0,
        why="Matches strong interest: reasoning and inference efficiency.",
    )
    defaults.update(kwargs)
    return radar.add(**defaults)


def test_an_item_lands_with_every_field_the_schema_requires():
    """The Radar collection is validated by the same Zod schema that
    guards posts, so a missing field fails `astro build` rather than
    showing up as a blank line in a digest."""
    item = _add(_radar())
    for field in ("id", "url", "title", "source", "section", "topics",
                  "qualityScore", "relevanceScore", "whyRelevant", "seenAt",
                  "status"):
        assert field in item, field
    assert item["status"] == "radar"


def test_why_relevant_is_never_blank_and_never_over_length():
    """§7.2: the one-sentence reason is how a mis-tuned profile becomes
    visible. A blank one makes the digest useless for its only job."""
    item = _add(_radar(), why="x" * 400)
    assert item["whyRelevant"]
    assert len(item["whyRelevant"]) <= 200


def test_seeing_the_same_item_again_refreshes_it_rather_than_duplicating():
    """An hourly run meets the same feed item until it falls off the
    feed. Without idempotence a week-long item would put seven identical
    lines in one digest."""
    radar = _radar()
    _add(radar, relevance=60.0)
    _add(radar, relevance=71.0)
    rows = radar._all()  # noqa: SLF001
    assert len(rows) == 1
    assert rows[0]["relevanceScore"] == 71.0


def test_two_feeds_carrying_one_url_are_one_item():
    radar = _radar()
    _add(radar, source="arXiv cs.LG", title="A finding")
    _add(radar, source="Hugging Face — Daily Papers", title="A Finding (mirror)")
    assert len(radar._all()) == 1  # noqa: SLF001


def test_the_id_is_stable_across_processes():
    """A Telegram reaction arrives hours after the digest was sent, in
    a different process. The id has to be a function of the item, not
    of a counter."""
    assert radar_id("https://example.com/a", "T") == radar_id(
        "https://example.com/a", "different title"
    )
    assert radar_id("", "T") != radar_id("", "U")


def test_promotion_records_the_post_it_became():
    radar = _radar()
    item = _add(radar)
    radar.set_status(item["id"], "promoted", promoted_to="a-slug")
    assert radar.find(item["id"])["status"] == "promoted"
    assert radar.find(item["id"])["promotedTo"] == "a-slug"


def test_retraction_dismisses_rather_than_deletes():
    """§11.2: a retracted post comes back to the Radar with status
    "dismissed". The record of the retraction is the point — deleting
    it would make a retraction indistinguishable from never having
    published."""
    radar = _radar()
    item = radar.demote_post(
        url="https://example.com/a", title="A post", source="OpenAI News",
        section="release", topics=["llms"], quality=70, relevance=60,
        why="Retracted.", slug="a-post",
    )
    assert item["status"] == "dismissed"
    assert item["promotedTo"] == "a-post"
    assert len(radar._all()) == 1  # noqa: SLF001


def test_only_the_three_documented_statuses_are_accepted():
    radar = _radar()
    item = _add(radar)
    for status in ("radar", "promoted", "dismissed"):
        assert radar.set_status(item["id"], status)
    try:
        radar.set_status(item["id"], "archived")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown status must not be accepted")


def test_only_the_four_documented_feedback_kinds_are_accepted():
    radar = _radar()
    item = _add(radar)
    for kind in ("interesting", "not_useful", "not_my_topic", "deep_dive"):
        assert radar.set_feedback(item["id"], kind)
    try:
        radar.set_feedback(item["id"], "meh")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown feedback kind must not be accepted")


def test_top_of_radar_is_ordered_by_relevance_and_excludes_promoted():
    """The digest's "Top of Radar (not published)" block. An item that
    was published is by definition not in it."""
    radar = _radar()
    for i, score in enumerate([40.0, 88.0, 61.0]):
        _add(radar, url=f"https://example.com/{i}", title=f"Item {i}", relevance=score)
    promoted = _add(radar, url="https://example.com/x", title="Published",
                    relevance=99.0)
    radar.set_status(promoted["id"], "promoted", promoted_to="slug")

    top = radar.top(limit=5)
    assert [t["relevanceScore"] for t in top] == [88.0, 61.0, 40.0]
    assert all(t["status"] == "radar" for t in top)


def test_since_is_what_the_daily_digest_reads():
    radar = _radar()
    fresh = _add(radar, url="https://example.com/fresh", title="Fresh")
    old = _add(radar, url="https://example.com/old", title="Old")
    old["seenAt"] = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    titles = [i["title"] for i in radar.since(hours=24)]
    assert "Fresh" in titles
    assert "Old" not in titles


def test_seen_at_defaults_to_now_not_to_the_articles_own_date():
    """Regression: passing the source's publication date scattered one
    sweep of 286 items across twenty-four monthly files, including one
    named "2026" from a malformed timestamp."""
    item = _add(_radar())
    assert item["seenAt"][:7] == month_key()
    assert len(month_key()) == 7


def test_the_month_file_is_valid_json_with_the_schema_shape():
    directory = Path(tempfile.mkdtemp(prefix="radar-test-"))
    radar = Radar(dry_run=True, directory=directory)
    _add(radar)
    radar.save()
    files = list(directory.glob("*.json"))
    assert len(files) == 1
    document = json.loads(files[0].read_text(encoding="utf-8"))
    assert document["month"] == files[0].stem
    assert isinstance(document["items"], list) and document["items"]


def test_the_radar_has_no_public_surface():
    """Decision A3, asserted against the repo rather than trusted to a
    comment. If a /radar/ route or feed ever appears, this fails."""
    pages = REPO_ROOT / "src" / "pages"
    assert not (pages / "radar").exists()
    assert not (pages / "radar.astro").exists()

    # Nothing in src/ may read the collection either — that is what
    # would put Radar items on a page without a route of their own.
    for path in (REPO_ROOT / "src").rglob("*"):
        if path.suffix not in (".astro", ".ts") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert 'getCollection("radar")' not in text, path
        assert "getCollection('radar')" not in text, path
