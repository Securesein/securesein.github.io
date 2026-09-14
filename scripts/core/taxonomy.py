"""
The three vocabularies, read from the same /taxonomy.json the Astro site
reads (src/taxonomy.ts).

Brief §3.6: nothing in `src/` or `scripts/` may hard-code a section, a
format or a topic string. This module is how the Python half keeps that
promise — every classifier prompt, every enum check and every budget
lookup goes through here, so retiring a section is one edit to one JSON
file rather than a grep across two languages.

The three axes (brief §3.1):

  section  why would someone read this?   -> frontmatter `kind`
  format   what shape is this piece?      -> frontmatter `format`
  topics   what is it technically about?  -> frontmatter `topics[]`, 1-3

An unrecognised value is DROPPED, never invented and never coerced onto
the nearest-looking neighbour. That rule is absolute and is enforced
here rather than asked for in a prompt.
"""

from __future__ import annotations

import json
from functools import lru_cache

from .constants import TAXONOMY_FILE


@lru_cache(maxsize=1)
def _document() -> dict:
    return json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))


def sections() -> dict[str, dict]:
    return _document()["sections"]


def formats() -> dict[str, dict]:
    return _document()["formats"]


def topics() -> dict[str, dict]:
    return _document()["topics"]


def section_slugs() -> list[str]:
    return list(sections())


def format_slugs() -> list[str]:
    return list(formats())


def topic_slugs() -> list[str]:
    return list(topics())


def is_section(slug: str) -> bool:
    return slug in sections()


def is_format(slug: str) -> bool:
    return slug in formats()


def is_topic(slug: str) -> bool:
    return slug in topics()


def valid_topics(candidates) -> list[str]:
    """Filter a model's suggested topics down to the closed vocabulary,
    de-duplicated, order preserved, capped at three.

    An unknown slug is dropped with no attempt to map it onto something
    close: "llm" is not silently turned into "llms", because a
    classifier that gets rewarded for near-misses learns to guess."""
    out: list[str] = []
    for slug in candidates or []:
        slug = str(slug).strip()
        if is_topic(slug) and slug not in out:
            out.append(slug)
    return out[:3]


def section_label(slug: str) -> str:
    return sections().get(slug, {}).get("label", slug)


def section_route(slug: str) -> str:
    return sections().get(slug, {}).get("href", "/")


def topic_prompt_block() -> str:
    """The closed topic list, rendered for a classifier prompt."""
    return "\n".join(
        f'- "{slug}": {info["label"]} — {info["description"]}'
        for slug, info in topics().items()
    )


def section_prompt_block() -> str:
    """The closed section list, rendered for a classifier prompt. Each
    section is described by the question it answers, which is what the
    classifier is actually being asked to match against."""
    return "\n".join(
        f'- "{slug}": {info["label"]} — {info["question"]} {info["description"]}'
        for slug, info in sections().items()
    )


def format_prompt_block() -> str:
    return "\n".join(
        f'- "{slug}": {info["label"]} — {info["description"]}'
        for slug, info in formats().items()
    )
