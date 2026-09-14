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
  html         no adapter here; these need a bespoke scraper and are
               skipped with a log line rather than silently ignored

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
        if source.type in ("html", "api", "git", "python_client"):
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
