"""
Two things that together were why Claude Opus 5.5 was never detected,
and why fixing that could have been expensive.

1. `type: html` sources were skipped outright, so Anthropic and xAI
   had no working primary trigger at all — every one of their primary
   entries was an html page. The release was on docs.claude.com the
   whole time; nothing could read it.

2. Turning seven skipped sources on at once is exactly the shape of a
   cost spike: every item on a new source is unseen, so dedup removes
   none of it, and the age filter cannot bound a page that carries no
   dates. A new source is therefore baselined on its first run, the
   same protection the channel itself already had for its own first
   run.

Both are asserted against fixture HTML rather than the live pages, so
these keep testing the parser after a vendor redesigns their site.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import feeds  # noqa: E402
from core.feeds import Item, Source, _fetch_html  # noqa: E402


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status


CHANGELOG = """
<html><body>
  <h1>Cookie settings</h1>
  <h2>September 22, 2026</h2>
  <ul>
    <li>We've launched Claude Opus 5.5 (claude-opus-5-5), a model for
        long-running agentic coding and knowledge work.</li>
    <li>Cache diagnostics is out of beta and no longer requires a header.</li>
    <li>short</li>
  </ul>
  <h2>September 21, 2026</h2>
  <ul><li>An unrelated billing change that is long enough to count as an item.</li></ul>
</body></html>
"""

INDEX = """
<html><body>
  <h2><a href="/news/grok-4-7">Introducing Grok 4.7</a></h2>
  <h2><a href="/news/support">How we scaled customer support</a></h2>
  <h3>All posts</h3>
</body></html>
"""


def _source(url="https://example.test/notes"):
    return Source(name="Test", url=url, type="html", tier="primary", vendor="test")


def test_changelog_splits_one_date_into_its_separate_changes(monkeypatch):
    """A single date holds a model launch next to a billing note. One
    item per date would hand the classifier both at once and ask it to
    call the day a release; one item per change lets the launch be
    judged on its own words."""
    monkeypatch.setattr(feeds, "_get", lambda url: FakeResponse(CHANGELOG))
    items = _fetch_html(_source(), limit=30)

    titles = [i.title for i in items]
    assert any("Opus 5.5" in t for t in titles), "the launch was not extracted"
    assert any("Cache diagnostics" in t for t in titles)
    assert len(items) == 3, f"expected the three long bullets, got {titles}"


def test_changelog_dates_come_from_the_heading(monkeypatch):
    """The release channel's age filter is the thing keeping a back
    catalogue out, and it can only work on real dates."""
    monkeypatch.setattr(feeds, "_get", lambda url: FakeResponse(CHANGELOG))
    items = _fetch_html(_source(), limit=30)
    launch = next(i for i in items if "Opus 5.5" in i.title)
    assert launch.published.startswith("2026-09-22")


def test_page_furniture_is_not_a_release_candidate(monkeypatch):
    """"Cookie settings" is a heading too. A page is one shape or the
    other, so a changelog never also yields index-shaped entries."""
    monkeypatch.setattr(feeds, "_get", lambda url: FakeResponse(CHANGELOG))
    items = _fetch_html(_source(), limit=30)
    assert not any("Cookie" in i.title for i in items)


def test_index_pages_use_the_heading_and_resolve_relative_links(monkeypatch):
    monkeypatch.setattr(feeds, "_get", lambda url: FakeResponse(INDEX))
    items = _fetch_html(_source("https://x.test/news"), limit=30)

    titles = [i.title for i in items]
    assert "Introducing Grok 4.7" in titles
    assert "All posts" not in titles, "navigation is not a post"
    grok = next(i for i in items if i.title == "Introducing Grok 4.7")
    assert grok.url == "https://x.test/news/grok-4-7"


def test_an_undated_entry_gets_no_date_rather_than_today(monkeypatch):
    """Defaulting to now is the one value that would defeat the age
    filter downstream: a three-year-old post would read as this
    morning's release."""
    monkeypatch.setattr(feeds, "_get", lambda url: FakeResponse(INDEX))
    items = _fetch_html(_source("https://x.test/news"), limit=30)
    assert all(i.published == "" for i in items)


def test_html_is_dispatched_rather_than_skipped(monkeypatch):
    monkeypatch.setattr(feeds, "_get", lambda url: FakeResponse(CHANGELOG))
    items = feeds.fetch(_source(), limit=30)
    assert items, "fetch() still skips html sources"


def test_a_brand_new_source_is_baselined_not_published():
    """Adding a feed must not be a spike. Everything on it is unseen by
    definition, so the first run records it and publishes nothing."""
    from channels import releases

    source = _source()
    items = [
        Item(id=f"id-{n}", title=f"Item {n} with a title long enough", url="u",
             source=source, summary="s", published="")
        for n in range(30)
    ]

    class Ctx:
        dry_run = True
        limit = None
        fixtures = None

    written: dict = {}
    original_fetch = releases.fetch
    original_seen = releases._seen
    original_remember = releases._remember
    try:
        releases.fetch = lambda src, limit=30: items
        # channel has run before, but this source has not
        releases._seen = lambda: ({"other"}, False, {"Some Other Source"})
        releases._remember = lambda ids, dry, srcs=None: written.update(
            ids=ids, sources=srcs
        )
        got = releases.gather(Ctx(), {"max_item_age_days": 14}, sources=[source])
    finally:
        releases.fetch = original_fetch
        releases._seen = original_seen
        releases._remember = original_remember

    assert got == [], "a new source published on its very first run"
    assert written["ids"] >= {i.id for i in items}, "the baseline was not recorded"
    assert "Test" in written["sources"], "the source was not marked as seen"
