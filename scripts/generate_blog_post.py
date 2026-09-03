"""
Turn a marked news item into a full English blog post and write it as
a new Markdown file in src/content/blog/, matching the Astro content
schema exactly (title, description, pubDate, tags, sourceUrl,
sourceName, author — see src/content.config.ts).

Two ways to run:

  python scripts/generate_blog_post.py --test <article-url>
      Generates one post from any article URL, standalone — doesn't
      touch data/marked.json. Use this to check output quality before
      wiring it into the real pipeline.

  python scripts/generate_blog_post.py
      Processes every item in data/marked.json with status "pending":
      writes a post file for each, then flips its status to
      "published". Runs as a step in
      .github/workflows/nieuwsbrief.yml, after process_callbacks.py.

Every post is published automatically, with author "ai" — no draft /
review step. Git is the safety net (a bad post is a `git revert` away),
matching the "geparkeerd voor later" decision in the project brief to
skip a manual approval step.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

from article_fetch import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MARKED_FILE = DATA_DIR / "marked.json"
BLOG_DIR = REPO_ROOT / "src" / "content" / "blog"
CATEGORIES_FILE = REPO_ROOT / "categories.json"

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
# Deliberately a stronger (and pricier) model than the Telegram summary
# step — this is the one piece of writing that actually gets published.
BLOG_MODEL = os.environ.get("OPENAI_BLOG_MODEL", "gpt-4o")

ARTICLE_MAX_CHARS = 8000
STYLE_EXAMPLE_COUNT = 2

client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Inputs: categories, style examples
# ---------------------------------------------------------------------------

def load_categories() -> dict:
    with open(CATEGORIES_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_style_examples() -> list[str]:
    """Existing posts, used as few-shot style examples so the model
    matches this blog's voice instead of writing generic AI-blog
    filler. Skips welcome.md — that one's personal, not representative
    of the AI-written posts this is meant to sound like."""
    posts = sorted(BLOG_DIR.glob("*.md"))
    posts = [p for p in posts if p.name != "welcome.md"]
    examples = []
    for path in posts[:STYLE_EXAMPLE_COUNT]:
        examples.append(path.read_text(encoding="utf-8"))
    return examples


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def build_prompt(task_block: str, categories: dict, style_examples: list[str]) -> str:
    """Shared scaffolding (voice, style examples, category list, JSON
    contract) around a task-specific block — see build_article_task()
    and build_concept_task()."""
    category_list = "\n".join(
        f'- "{slug}": {info["label"]} — {info["description"]}'
        for slug, info in categories.items()
    )
    examples_block = "\n\n---\n\n".join(style_examples) or "(no examples available)"

    return f"""You are writing a blog post for "securesein", a blog about
applied AI, enterprise mobility, and the Microsoft ecosystem — written
from hands-on practice, not press releases. Match the tone and
structure of the example posts below: direct, concrete, no marketing
fluff, no "in today's fast-paced world" openers.

EXAMPLE POSTS (for tone/structure only — write about the new topic below,
not these):

{examples_block}

---

{task_block}

---

VALID CATEGORIES (pick exactly 1, or 2 if genuinely both apply — use
the exact slug in quotes, nothing else):
{category_list}

Return ONLY a JSON object with exactly these keys, nothing else:
{{
  "title": "a clear, specific headline for the post",
  "description": "one sentence, shown under the title as a lede",
  "tags": ["one-or-two-category-slugs-from-the-list-above"],
  "body": "the full post body in Markdown, no frontmatter, no h1 (the title is rendered separately) — start with a short lead paragraph, use ## for section headings"
}}"""


def build_article_task(title: str, source: str, article_text: str) -> str:
    return f"""NEW ARTICLE TO WRITE ABOUT
Title: "{title}"
Source: {source}

Article text:
{article_text}"""


def build_concept_task(topic: str, article_title: str, source: str, article_text: str) -> str:
    return f"""Write an EXPLAINER post about the following concept/topic —
this is the actual subject of the post, not the article below:

TOPIC: "{topic}"

The post should stand on its own as an explanation of the topic for a
technical reader — what it is, why it matters, how it's typically used
or implemented. Do NOT structure this as a summary or rewrite of the
article below; use it only as background/reference for a concrete,
current example, and cite it as the source.

BACKGROUND ARTICLE (reference only, not the subject)
Title: "{article_title}"
Source: {source}

Article text:
{article_text}"""


def _call_openai(prompt: str, categories: dict) -> dict | None:
    try:
        response = client.chat.completions.create(
            model=BLOG_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        print(f"    OpenAI blog generation failed: {e}", file=sys.stderr)
        return None

    # Light fallback — never fully trust the shape of an API response,
    # even a "structured" one. See project brief.
    if not data.get("title") or not data.get("body"):
        print(f"    Model response missing title/body, skipping: {data}", file=sys.stderr)
        return None

    valid_tags = [t for t in data.get("tags", []) if t in categories]
    if not valid_tags:
        valid_tags = ["meta"]

    return {
        "title": str(data["title"]).strip(),
        "description": str(data.get("description", "")).strip() or "Read more below.",
        "tags": valid_tags,
        "body": str(data["body"]).strip(),
    }


def generate_post(title: str, source: str, link: str, categories: dict, style_examples: list[str]) -> dict | None:
    """Direct write-up of the article itself — the ☆ button flow."""
    article_text = fetch_article_text(link, ARTICLE_MAX_CHARS)
    if len(article_text) < 200:
        print(f"    Skipping — couldn't fetch enough article text from {link}", file=sys.stderr)
        return None

    task = build_article_task(title, source, article_text)
    return _call_openai(build_prompt(task, categories, style_examples), categories)


def generate_concept_post(
    topic: str, article_title: str, source: str, link: str, categories: dict, style_examples: list[str]
) -> dict | None:
    """Explainer about a concept the user named in a reply — the
    article is background/reference, not the subject, so (unlike
    generate_post) a thin or failed scrape doesn't block this: the
    model can still write the explainer from its own knowledge of the
    topic, just with less concrete grounding to cite."""
    article_text = fetch_article_text(link, ARTICLE_MAX_CHARS)
    if len(article_text) < 200:
        print(f"    Note: little/no article text available from {link} — "
              f"writing from general knowledge of the topic instead.", file=sys.stderr)
        article_text = "(not available)"

    task = build_concept_task(topic, article_title, source, article_text)
    return _call_openai(build_prompt(task, categories, style_examples), categories)


# ---------------------------------------------------------------------------
# Writing the post file
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "post"


def unique_slug(base_slug: str) -> str:
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    slug = base_slug
    n = 2
    while (BLOG_DIR / f"{slug}.md").exists():
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def write_post_file(post: dict, source_url: str, source_name: str) -> str:
    slug = unique_slug(slugify(post["title"]))
    pub_date = time.strftime("%Y-%m-%d")
    tags_yaml = ", ".join(f'"{t}"' for t in post["tags"])

    frontmatter = f"""---
title: {json.dumps(post["title"])}
description: {json.dumps(post["description"])}
pubDate: {pub_date}
tags: [{tags_yaml}]
sourceUrl: {json.dumps(source_url)}
sourceName: {json.dumps(source_name)}
author: "ai"
---

{post["body"]}
"""
    path = BLOG_DIR / f"{slug}.md"
    path.write_text(frontmatter, encoding="utf-8")
    return slug


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_marked() -> dict:
    if not MARKED_FILE.exists():
        return {}
    with open(MARKED_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_marked(marked: dict) -> None:
    with open(MARKED_FILE, "w", encoding="utf-8") as f:
        json.dump(marked, f, ensure_ascii=False, indent=2)


def main() -> None:
    categories = load_categories()
    style_examples = load_style_examples()
    marked = load_marked()

    pending = {sid: item for sid, item in marked.items() if item.get("status") == "pending"}
    print(f"{len(pending)} item(s) pending a blog post.")

    for sid, item in pending.items():
        kind = item.get("kind", "article")
        if kind == "concept":
            print(f"  Writing concept post \"{item['topic']}\" (from: {item['title'][:50]})...")
            post = generate_concept_post(
                item["topic"], item["title"], item["source"], item["link"], categories, style_examples
            )
        else:
            print(f"  Writing: {item['title'][:60]}...")
            post = generate_post(item["title"], item["source"], item["link"], categories, style_examples)

        if post is None:
            continue  # leave status "pending" — will retry next run

        slug = write_post_file(post, item["link"], item["source"])
        print(f"    -> src/content/blog/{slug}.md")

        marked[sid]["status"] = "published"
        marked[sid]["slug"] = slug
        marked[sid]["published_at"] = time.time()
        save_marked(marked)  # save after each post, not just at the end

    print("Done.")


def run_test(url: str) -> None:
    """Generates one post from an arbitrary URL, independent of
    data/marked.json — for checking output quality/format first."""
    categories = load_categories()
    style_examples = load_style_examples()
    print(f"Style examples loaded: {len(style_examples)}")

    post = generate_post("(test article)", "Test source", url, categories, style_examples)
    if post is None:
        print("Generation failed — see error above.")
        raise SystemExit(1)

    slug = write_post_file(post, url, "Test source")
    print(f"Wrote src/content/blog/{slug}.md — inspect it, then delete if it was just a test.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        if idx + 1 >= len(sys.argv):
            print("Usage: python scripts/generate_blog_post.py --test <article-url>")
            raise SystemExit(1)
        run_test(sys.argv[idx + 1])
    else:
        main()
