"""
Schema-correct Markdown emission, for every channel.

The Zod schema in src/content.config.ts is the only quality gate that
runs after a post is written, so this module's whole job is to never
hand it something it will reject. Everything a channel is *not allowed*
to assert lives here rather than in each channel:

  credit is always "scout"
      Scout cannot claim a post was human-directed. A pipeline that
      could would make every credit line on the site worthless.
  kind (the section) comes from the classifier
      constrained to the closed section vocabulary, never free text.
  format is always present
      every post has a shape under the three-axis model, and the schema
      requires it.
  source is always present
      except for the one legacy path (a custom Telegram brief) that
      genuinely has no article behind it.
  topics come from the closed list
      an unknown slug is dropped, never coerced into something close.
  scout{} is always present
      §4.1 rule 5: an auto-published post must carry the reason it was
      published. Rendering it is not optional and there is no code path
      that omits it, because a post with no `whyRelevant` is a post
      whose mis-ranking nobody can see.

The YAML is written by hand rather than via a serialiser, exactly as it
was before the refactor, because the schema-relevant surface is a dozen
flat scalars plus two small objects and a dependency buys nothing.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .constants import BLOG_DIR


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "post"


def unique_slug(base_slug: str, blog_dir: Path = BLOG_DIR) -> str:
    blog_dir.mkdir(parents=True, exist_ok=True)
    slug = base_slug
    n = 2
    while (blog_dir / f"{slug}.md").exists():
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def _yaml_list(values) -> str:
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


def render(
    post: dict,
    *,
    kind: str,
    fmt: str,
    model: str,
    source_url: str | None = None,
    source_name: str | None = None,
    source_published: str | None = None,
    release: dict | None = None,
    benchmark_refs: list[str] | None = None,
    scout: dict | None = None,
    pub_date: str | None = None,
) -> str:
    """The full file contents — frontmatter plus body."""
    lines = [
        "---",
        f'title: {json.dumps(post["title"])}',
        f'description: {json.dumps(post["description"])}',
        f"pubDate: {pub_date or time.strftime('%Y-%m-%d')}",
        f"kind: {json.dumps(kind)}",
        f"format: {json.dumps(fmt)}",
        f"topics: {_yaml_list(post['topics'])}",
        'credit: "scout"',
        f"model: {json.dumps(model)}",
    ]
    if source_url:
        lines.append("source:")
        lines.append(f"  url: {json.dumps(source_url)}")
        lines.append(f"  publisher: {json.dumps(source_name or 'Unknown')}")
        if source_published:
            lines.append(f"  publishedAt: {source_published}")
    if release:
        lines.append("release:")
        lines.append(f"  vendor: {json.dumps(release['vendor'])}")
        lines.append(f"  family: {json.dumps(release['family'])}")
        if release.get("version"):
            lines.append(f"  version: {json.dumps(release['version'])}")
        lines.append(f"  eventType: {json.dumps(release['eventType'])}")
        lines.append(f"  openWeights: {str(bool(release.get('openWeights'))).lower()}")
        lines.append(f"  modality: {_yaml_list(release.get('modality') or ['text'])}")
    if benchmark_refs:
        lines.append(f"benchmarkRefs: {_yaml_list(benchmark_refs)}")
    if scout:
        # §7.2: the one-sentence reason is not decoration. It is how a
        # mis-tuned profile becomes visible in the digest, and it is the
        # first thing to read when the wrong things start being
        # published. Truncated to the schema's 300 chars here rather
        # than hoping the model respected the instruction.
        lines.append("scout:")
        lines.append(f"  qualityScore: {round(float(scout['qualityScore']), 1)}")
        lines.append(f"  relevanceScore: {round(float(scout['relevanceScore']), 1)}")
        lines.append(f"  whyRelevant: {json.dumps(str(scout['whyRelevant'])[:300])}")
        lines.append(f"  candidateId: {json.dumps(scout['candidateId'])}")
    lines += ["---", "", post["body"].strip(), ""]
    return "\n".join(lines)


def write_post(text: str, title: str, blog_dir: Path = BLOG_DIR) -> str:
    slug = unique_slug(slugify(title), blog_dir)
    (blog_dir / f"{slug}.md").write_text(text, encoding="utf-8")
    return slug


# --- updating an existing post rather than writing a new one --------

UPDATE_MARKER = "## Updates"


def append_update(path: Path, line: str, when: str) -> None:
    """§6.1 step 5: a release entity seen again inside its cooldown but
    carrying a material new fact updates the post it already has — a
    dated line appended and `updatedDate` set — instead of creating a
    second post about one release. This consumes no budget and mints no
    new URL, which is the entire point."""
    text = path.read_text(encoding="utf-8")

    if re.search(r"^updatedDate:", text, re.M):
        text = re.sub(r"^updatedDate:.*$", f"updatedDate: {when}", text, count=1, flags=re.M)
    else:
        text = re.sub(r"^(pubDate:.*)$", rf"\1\nupdatedDate: {when}", text, count=1, flags=re.M)

    entry = f"- **{when}** — {line.strip()}"
    if UPDATE_MARKER in text:
        text = text.rstrip() + f"\n{entry}\n"
    else:
        text = text.rstrip() + f"\n\n{UPDATE_MARKER}\n\n{entry}\n"
    path.write_text(text, encoding="utf-8")


# --- reading what is already published -------------------------------


def read_frontmatter(path: Path) -> dict:
    """Enough of a YAML reader for the flat scalar fields and the two
    one-level objects this pipeline needs. Deliberately not a
    dependency — carried over unchanged from generate_blog_post.py."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not match:
        return {}
    data: dict = {}
    section = None
    for line in match.group(1).split("\n"):
        if line.startswith("  ") and section:
            key, _, value = line.strip().partition(":")
            data.setdefault(section, {})[key.strip()] = value.strip().strip('"')
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not value:
            section = key
        else:
            section = None
            data[key] = value.strip('"')
    return data


def _topics_of(path: Path) -> list[str]:
    """The topics line, parsed out of frontmatter. Needed by the topic
    starvation bonus (§7.1), which has to know when each topic was last
    touched — and the posts themselves are the only record of that."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^topics:\s*\[(.*?)\]\s*$", text, re.M)
    if not match:
        return []
    return [t.strip().strip('"') for t in match.group(1).split(",") if t.strip()]


def existing_posts(blog_dir: Path = BLOG_DIR) -> list[dict]:
    """Title, date, kind and source URL of everything already
    published — the input to the duplicate check."""
    posts = []
    for path in sorted(blog_dir.glob("*.md")):
        data = read_frontmatter(path)
        if not data.get("title"):
            continue
        posts.append({
            "slug": path.stem,
            "title": data["title"],
            "pub_date": data.get("pubDate", ""),
            "kind": data.get("kind", "research"),
            "format": data.get("format", "news"),
            "topics": _topics_of(path),
            "source_url": (data.get("source") or {}).get("url", ""),
            "path": path,
        })
    return posts
