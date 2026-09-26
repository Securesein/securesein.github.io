"""
Fetching and parsing every kind of source this pipeline reads.

`feeds.json` is a bare list of `{naam, url}`; the two new files wrap
their entries in `{"feeds": [...]}` / `{"sources": [...]}` and add
`type`, `tier`, `vendor` and `verified`. One loader handles all three
shapes so no caller has to know which file it came from.

Five source types, because "an RSS feed" stopped being a complete
description of where release news lives some time ago:

  rss / atom   feedparser
  json         a plain JSON endpoint
  hf_api       the Hugging Face Hub REST API, public and tokenless,
               sorted by createdAt — the only first-party, timestamped
               release signal several open-weights labs have
  html         vendor changelog and announcement pages that publish
               no feed at all. Added 2026-09-26: these used to be
               skipped, which meant Anthropic and xAI had no working
               primary trigger of any kind — Claude Opus 5.5 was
               announced on docs.claude.com and the pipeline could not
               read the page it was announced on.

`tier` is enforced in *code*, not in a prompt (brief §6.2): only a
`primary` source can trigger a post, a `corroborating` source can add
score to a candidate that already exists, and a `community` source is
context and can never do either. A prompt asked to respect tiering
would respect it most of the time, which is the wrong number.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .constants import FETCH_TIMEOUT, USER_AGENT

TIER_PRIMARY = "primary"
TIER_CORROBORATING = "corroborating"
TIER_COMMUNITY = "community"


@dataclass
class Source:
    name: str
    url: str
    type: str = "rss"
    tier: str = TIER_PRIMARY
    vendor: str = "-"
    verified: bool = False
    role: str = ""
    note: str = ""
    in_scope: bool = True

    @property
    def may_trigger(self) -> bool:
        return self.tier == TIER_PRIMARY


@dataclass
class Item:
    """One candidate, normalised across every source type."""

    id: str
    title: str
    url: str
    source: Source
    summary: str = ""
    published: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def vendor(self) -> str:
        return self.source.vendor


def load_sources(path: Path) -> list[Source]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, list):  # the original feeds.json shape
        rows = document
    else:
        rows = document.get("feeds") or document.get("sources") or []
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("naam"):
            continue
        out.append(
            Source(
                name=row["naam"],
                url=row.get("url", ""),
                type=row.get("type", "rss"),
                tier=row.get("tier", TIER_PRIMARY),
                vendor=row.get("vendor", "-"),
                verified=bool(row.get("verified", False)),
                role=row.get("role", ""),
                note=row.get("note", ""),
                in_scope=bool(row.get("inScope", True)),
            )
        )
    return out


def load_fixture(path: Path) -> list[Item]:
    """Recorded source data, for running a channel against a known
    input with no network. A fixture carries its own `source` block per
    item, so tiering — which decides what may trigger a post at all —
    is exercised rather than assumed.

    This is how the scoring rubric and the entity dedup are tested: a
    week of real hourly runs is not something a build can wait for, and
    a rubric you cannot replay is a rubric you cannot tune."""
    document = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for row in document.get("items", []):
        source_row = row.get("source", {})
        source = Source(
            name=source_row.get("naam", "(fixture)"),
            url=source_row.get("url", ""),
            type=source_row.get("type", "rss"),
            tier=source_row.get("tier", TIER_PRIMARY),
            vendor=source_row.get("vendor", "-"),
            verified=True,
        )
        items.append(
            Item(
                id=row.get("id") or row.get("url", ""),
                title=row.get("title", ""),
                url=row.get("url", ""),
                source=source,
                summary=row.get("summary", ""),
                published=row.get("published", ""),
                extra=row.get("extra", {}),
            )
        )
    return items


# --- fetching -------------------------------------------------------


def _get(url: str, timeout: int = FETCH_TIMEOUT):
    import requests

    return requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})


def item_id(entry) -> str:
    """Stable unique id for a feed item: guid if present, else the link.
    Carried over verbatim from fetch_and_notify.py — changing it would
    make every already-seen item look new exactly once."""
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def short_id(full_id: str) -> str:
    return hashlib.sha256(full_id.encode("utf-8")).hexdigest()[:16]


def _iso(value: str) -> str:
    """Best-effort ISO date out of whatever a feed calls a timestamp."""
    if not value:
        return ""
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def fetch(source: Source, limit: int = 30) -> list[Item]:
    """Everything currently visible at this source, newest first where
    the source says so. Never raises: a dead source is one empty list,
    not a dead run."""
    if not source.url or source.url == "-" or not source.in_scope:
        return []
    try:
        if source.type in ("rss", "atom"):
            return _fetch_feed(source, limit)
        if source.type == "hf_api":
            return _fetch_hf(source, limit)
        if source.type == "json":
            return _fetch_json(source, limit)
        if source.type == "html":
            return _fetch_html(source, limit)
        if source.type in ("api", "git", "python_client"):
            print(
                f"    {source.name}: type '{source.type}' needs a bespoke adapter "
                f"— skipped, not failed.",
                file=sys.stderr,
            )
            return []
        print(f"    {source.name}: unknown type '{source.type}' — skipped.", file=sys.stderr)
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"    {source.name}: fetch failed ({exc}) — skipped.", file=sys.stderr)
        return []


def _fetch_feed(source: Source, limit: int) -> list[Item]:
    import feedparser

    response = _get(source.url)
    if response.status_code != 200:
        print(f"    {source.name}: HTTP {response.status_code}", file=sys.stderr)
        return []
    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries[:limit]:
        items.append(
            Item(
                id=item_id(entry),
                title=entry.get("title", "(no title)"),
                url=entry.get("link", ""),
                source=source,
                summary=(entry.get("summary", "") or "")[:2000],
                published=_iso(entry.get("published", "") or entry.get("updated", "")),
            )
        )
    return items


_DATE_HEADING = re.compile(
    r"^((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\s+(\d{1,2}),\s*(\d{4})"
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _heading_date(text: str) -> str:
    """ISO date out of a 'September 22, 2026' heading, or ''."""
    match = _DATE_HEADING.match(text.strip())
    if not match:
        return ""
    month = _MONTHS.get(match.group(1)[:3].lower())
    if not month:
        return ""
    try:
        return datetime(int(match.group(3)), month, int(match.group(2)),
                        tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ""


def _fetch_html(source: Source, limit: int) -> list[Item]:
    """Vendor changelog and announcement pages that publish no feed.

    Two shapes, because the pages come in two:

    - A CHANGELOG keyed by date ("September 22, 2026"), where one date
      holds several unrelated changes — a billing note, a compliance
      change and a model launch all sit under the same heading. Each
      bullet becomes its own item rather than one item per date, so a
      launch is classified on its own words instead of being averaged
      in with whatever else shipped that day.
    - An INDEX keyed by post title ("Introducing Grok 4.7"), the
      ordinary blog listing, where the heading is the item.

    Deliberately conservative about dates. There is no feed to trust
    here, so an entry with no date on the page gets no date rather than
    today's: the release channel's age filter is what stops a back
    catalogue being read as this morning, and defaulting to now is
    precisely the value that would defeat it.
    """
    from bs4 import BeautifulSoup

    response = _get(source.url)
    if response.status_code != 200:
        print(f"    {source.name}: HTTP {response.status_code}", file=sys.stderr)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()

    base = "/".join(source.url.split("/")[:3])
    items: list[Item] = []
    seen_text: set[str] = set()

    headings = soup.find_all(re.compile("^h[1-4]$"))
    # Decide the shape once, for the whole page, rather than per
    # heading. A changelog also carries page furniture — "Cookie
    # settings", "On this page" — and treating those as index-shaped
    # entries turns cookie banners into release candidates.
    is_changelog = any(
        _heading_date(re.sub(r"[-]", "", h.get_text(" ", strip=True)).strip())
        for h in headings
    )

    for heading in headings:
        # these doc sites append an anchor-link glyph from the private
        # use area to every heading
        label = re.sub(r"[-]", "", heading.get_text(" ", strip=True)).strip()
        if not label:
            continue

        published = _heading_date(label)

        if published:
            for node in heading.find_all_next():
                if node.name and re.match("^h[1-4]$", node.name):
                    break
                if node.name not in ("li", "p"):
                    continue
                text = node.get_text(" ", strip=True)
                if len(text) < 30 or text in seen_text:
                    continue
                seen_text.add(text)
                anchor = heading.get("id") or ""
                items.append(Item(
                    id=short_id(f"{source.url}#{text[:160]}"),
                    title=text[:180],
                    url=f"{source.url}#{anchor}" if anchor else source.url,
                    source=source,
                    summary=text[:2000],
                    published=published,
                ))
                if len(items) >= limit:
                    return items
        elif not is_changelog:
            if len(label) < 12 or label in seen_text:
                continue
            link = (heading.find("a", href=True)
                    or heading.find_parent("a", href=True)
                    or heading.find_next("a", href=True))
            href = link["href"] if link is not None else ""
            if href.startswith("/"):
                href = base + href
            seen_text.add(label)
            items.append(Item(
                id=short_id(f"{source.url}#{label}"),
                title=label[:180],
                url=href or source.url,
                source=source,
                summary=label[:2000],
                published="",
            ))
            if len(items) >= limit:
                return items

    return items


def _fetch_json(source: Source, limit: int) -> list[Item]:
    response = _get(source.url)
    response.raise_for_status()
    payload = response.json()
    rows = payload if isinstance(payload, list) else [payload]
    items = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        identifier = str(row.get("id") or row.get("_id") or row.get("title") or "")
        items.append(
            Item(
                id=identifier,
                title=str(row.get("title") or identifier),
                url=str(row.get("url") or source.url),
                source=source,
                published=_iso(str(row.get("publishedAt") or row.get("createdAt") or "")),
                extra=row,
            )
        )
    return items


# Quantisations, GGUF conversions and community re-uploads are not
# releases. Requiring the org to be the vendor's canonical org handles
# most of it (brief §10); this catches the rest, which the labs
# themselves publish alongside the real thing.
HF_NOISE = re.compile(
    r"(gguf|awq|gptq|int4|int8|fp8|bnb|4bit|8bit|mlx|onnx|openvino|"
    r"-quantized|-quant|-exl2|-ggml)",
    re.I,
)


def _fetch_hf(source: Source, limit: int) -> list[Item]:
    """A newly appearing repo under a tracked org is a `new_model`
    candidate. The org filter is already in the URL (`author=`); this
    only has to drop the derivative uploads."""
    response = _get(source.url)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        return []
    items = []
    for row in rows[:limit]:
        repo = str(row.get("modelId") or row.get("id") or "")
        if not repo:
            continue
        if HF_NOISE.search(repo):
            continue
        items.append(
            Item(
                id=f"hf:{repo}",
                title=repo,
                url=f"https://huggingface.co/{repo}",
                source=source,
                published=_iso(str(row.get("createdAt") or "")),
                extra={
                    "tags": row.get("tags", []),
                    "pipeline_tag": row.get("pipeline_tag"),
                    "downloads": row.get("downloads"),
                },
            )
        )
    return items


# --- article text ---------------------------------------------------

FETCH_TIMEOUT_ARTICLE = 15
ARTICLE_USER_AGENT = "Mozilla/5.0 (compatible; securesein-pipeline/1.0)"


def fetch_article_text(url: str, max_chars: int) -> str:
    """Best-effort plain-text scrape, moved here from the old
    scripts/article_fetch.py so there is one fetch implementation for
    every channel. Behaviour, timeout and user-agent are unchanged:
    returns "" on any failure so callers fall back to something else
    rather than crashing the run."""
    if not url:
        return ""
    import requests

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # The contract is "returns '' on any failure so callers fall
        # back instead of crashing the run", and a missing dependency is
        # a failure like any other. beautifulsoup4 is in
        # scripts/requirements.txt and present in CI; a developer
        # running a dry run without it should get a channel that
        # publishes nothing, not a traceback.
        print(
            "    beautifulsoup4 is not installed — cannot read article text. "
            "`pip install -r scripts/requirements.txt`",
            file=sys.stderr,
        )
        return ""

    try:
        response = requests.get(
            url,
            timeout=FETCH_TIMEOUT_ARTICLE,
            headers={"User-Agent": ARTICLE_USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]
