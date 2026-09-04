"""
Turn a marked news item into a full English blog post and write it as
a new Markdown file in src/content/blog/, matching the Astro content
schema exactly (title, description, pubDate, tags, sourceUrl,
sourceName, author — see src/content.config.ts).

Two kinds of marked item, from process_callbacks.py:
- "article" (default): a reply to an article's Telegram message.
  Writes about that article, optionally steered by the reply's text
  ("instructions" — e.g. "focus on pricing"), or with full creative
  freedom if the reply was empty.
- "custom": a plain message, not a reply — a from-scratch post with
  no source article, using the message text as the brief.

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

# Length instructions alone (however forceful) reliably underperform
# for this model — it converges on ~700 words regardless. Below
# MIN_WORDS, we ask it to expand the actual draft instead of just
# repeating "write more" in a fresh prompt; that's far more reliable.
MIN_WORDS = 850
TARGET_WORDS = 1200

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

def build_system_prompt(categories: dict, style_examples: list[str]) -> str:
    """Shared scaffolding (voice, style examples, category list, JSON
    contract) — sent as the system message, with the specific task
    (see build_article_task() etc.) as the user message. Splitting
    them this way, instead of one long user message, makes the model
    noticeably more likely to actually follow the hard constraints
    below (length, structure) rather than treating them as background
    color."""
    category_list = "\n".join(
        f'- "{slug}": {info["label"]} — {info["description"]}'
        for slug, info in categories.items()
    )
    examples_block = "\n\n---\n\n".join(style_examples) or "(no examples available)"

    return f"""You are writing a blog post for "securesein", a blog about
applied AI, enterprise mobility, and the Microsoft ecosystem — written
from hands-on practice, not press releases.

AUDIENCE: technical readers — developers, IT/sysadmins, enterprise
architects — who are comfortable with technology in general but are
NOT AI/ML specialists. This is a hard rule, not a suggestion: any
AI/ML-specific term, architecture name, training technique, or
evaluation metric you use (e.g. "fine-tuning", "embeddings",
"inference", "context window", "RAG", "multimodal", "bidirectional
Transformer", "diffusion objective", "nDCG@10", or anything similarly
jargony) must be immediately followed by a short plain-language
clarification of what it means or why it matters — a clause or a
sentence, not a glossary entry, but never leave a reader to just take
the term on faith. If a paragraph would otherwise read like a spec
sheet (a string of named techniques/numbers with no plain-language
throughline), rewrite it so a smart non-AI-specialist could follow the
actual point being made.

VOICE: write like an engaged human blogger, not a press release, a
Wikipedia summary, or a bullet-point status report:
- Open with a real introduction — a hook, a bit of context, or a
  concrete scenario that draws the reader in. Don't start by just
  restating the headline as a flat declarative sentence.
- Have an actual point of view. React to what's notable or surprising,
  connect it to something the reader would recognize from their own
  work, don't just list facts in order.
- Vary sentence length and structure the way a real writer does. Avoid
  a rigid "announcement -> implications -> conclusion" formula unless
  it genuinely fits this topic.
- Still no marketing fluff or hype ("game-changing", "in today's
  fast-paced world", etc.) — human and engaging doesn't mean breathless.
- Give it room to breathe — don't rush to wrap up in three short
  paragraphs if the topic has more to say.

STRUCTURE: this must read as one continuous, cumulative explanation —
never a set of independent, interchangeable sections bolted together
under headings. Every section has to build on what the previous one
just established: refer back to concepts you already introduced by
name, extend them, complicate them, apply them — don't introduce a
fresh, disconnected angle just because it's related to the topic.
Before adding a facet (an analogy, a cost angle, a "why it matters for
developers" aside), ask: does this deepen what's already been
explained, or is it a different mini-topic wearing the same headline?
If a section could be lifted out and dropped into an unrelated article
about the same topic without rewriting a word, that's the failure mode
— rewrite it so it only makes sense here, after what came before it.
Go deep enough that a technical-but-not-AI-specialist reader finishes
with real, durable understanding — able to reason about this concept
next time they hit it, not just recall a definition. Add depth by
explaining mechanism and following through on implications, not by
piling on more loosely-related sub-topics.

LENGTH & EXAMPLES — hard requirement, not a suggestion: this post must
be AT LEAST 900 words, target 1100-1500. A post under 900 words is a
failed draft, full stop — treat that as a signal you didn't develop
your examples enough, not as an acceptable outcome for a shorter
topic. The way to hit this honestly (not by padding) is examples: at
least TWO points in the post need a fully worked example — a
scenario, a before/after, a walkthrough — shown happening step by
step with real specifics (concrete numbers, what a user or developer
literally sees or does at each stage). "For example, X helps with Y"
is not a worked example, it's a gesture at one; a real one runs a
paragraph or more of concrete detail. If you're tempted to end a
section in one or two sentences, that's exactly where a worked example
belongs instead. Every added paragraph still has to obey the STRUCTURE
rule above (build on what came before) — you're going deeper and
wider on the same throughline, not padding with tangents.

Concretely: write 6-8 sections (##), most of them 2-4 paragraphs, with
at least two sections built around one of those fully worked examples
(150+ words each) rather than a one-line mention. Before you write a
conclusion, check: am I under 1100 words? If so, you are not done —
go deeper on an angle you haven't covered yet (a failure mode, a
concrete implementation detail, how this is typically handled in
practice) rather than padding the conclusion to compensate.

The example posts below are for topical scope and this blog's subject
matter only — they're shorter and drier than the voice above calls
for, so don't mimic their brevity, override it:

{examples_block}

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


def build_article_task(title: str, source: str, article_text: str, instructions: str | None = None) -> str:
    instructions_block = ""
    if instructions:
        instructions_block = f"""

ADDITIONAL INSTRUCTIONS FROM THE USER — follow these closely (they
might redirect the angle entirely, e.g. toward a broader concept the
article only touches on; that's fine, the article just needs to stay
the anchor/reference point), but don't let them override the
AUDIENCE/VOICE/STRUCTURE rules above (still explain jargon, still
build cumulatively, still hit the length target):
"{instructions}\""""

    return f"""NEW ARTICLE TO WRITE ABOUT
Title: "{title}"
Source: {source}

Article text:
{article_text}{instructions_block}"""


def build_custom_task(brief: str) -> str:
    return f"""The user requested this post directly, from scratch —
there is no source article to reference or cite. Their message below
is the brief: it names the topic and may also include specific
requirements (things to cover, an angle to take, a style to write in,
etc). Follow it as closely as possible while still fitting the voice
and audience described above. If this reads as an explainer (it
usually will), the STRUCTURE rule above matters most: build one idea
on top of the previous one toward a real, connected understanding —
don't cover separate facets as if they were independent mini-sections
with nothing to do with each other.

USER'S REQUEST (verbatim):
{brief}"""


def _expand_body(body: str, task: str, system_prompt: str) -> str | None:
    """Second pass, only used when the first draft came in under
    MIN_WORDS: asks the model to expand the existing draft (not
    rewrite from scratch) by adding worked examples and an uncovered
    angle. Returns the expanded body, or None if this pass fails or
    doesn't actually help."""
    word_count = len(body.split())
    expand_task = f"""Below is a draft blog post body that came in at
{word_count} words — under the {MIN_WORDS}-word minimum. Expand it to
at least {TARGET_WORDS} words:
- add 1-2 more fully worked examples (150+ words each, concrete
  specifics — real numbers, what a user/developer sees at each step)
  to sections that currently just gesture at a point
- go deeper on an angle the draft hasn't covered yet (a failure mode,
  an implementation detail, how this is handled in practice)

Do not shorten, remove, or rewrite what's already good — keep the
existing structure, voice, and throughline; only add material that
connects into it, per the STRUCTURE rule. Return the SAME JSON shape
as before (title, description, tags, body) with the expanded body.

ORIGINAL TASK (for context):
{task}

DRAFT BODY TO EXPAND:
{body}"""

    try:
        response = client.chat.completions.create(
            model=BLOG_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": expand_task},
            ],
            response_format={"type": "json_object"},
            temperature=0.75,
        )
        expanded = json.loads(response.choices[0].message.content or "{}")
        expanded_body = str(expanded.get("body", "")).strip()
    except Exception as e:
        print(f"    Expansion pass failed, keeping the {word_count}-word draft: {e}", file=sys.stderr)
        return None

    if len(expanded_body.split()) <= word_count:
        return None  # didn't actually help — keep the original
    return expanded_body


def _call_openai(task: str, categories: dict, style_examples: list[str]) -> dict | None:
    system_prompt = build_system_prompt(categories, style_examples)
    try:
        response = client.chat.completions.create(
            model=BLOG_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ],
            response_format={"type": "json_object"},
            temperature=0.75,
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

    body = str(data["body"]).strip()
    word_count = len(body.split())
    if word_count < MIN_WORDS:
        print(f"    Draft was {word_count} words (under {MIN_WORDS}) — expanding...", file=sys.stderr)
        expanded = _expand_body(body, task, system_prompt)
        if expanded:
            body = expanded
            print(f"    Expanded to {len(body.split())} words.", file=sys.stderr)

    return {
        "title": str(data["title"]).strip(),
        "description": str(data.get("description", "")).strip() or "Read more below.",
        "tags": valid_tags,
        "body": body,
    }


def generate_post(
    title: str, source: str, link: str, categories: dict, style_examples: list[str],
    instructions: str | None = None,
) -> dict | None:
    """Write-up of the article, optionally steered by `instructions`
    (from a reply's text — see process_callbacks.py). With
    instructions, a thin/failed scrape doesn't block this (the user
    may have redirected toward a broader concept anyway, needing the
    article only as an anchor) — the model falls back to its own
    knowledge. Without instructions, the article text is the whole
    point, so a failed scrape means retrying next run instead."""
    article_text = fetch_article_text(link, ARTICLE_MAX_CHARS)
    if len(article_text) < 200:
        if instructions:
            print(f"    Note: little/no article text available from {link} — "
                  f"writing from general knowledge instead.", file=sys.stderr)
            article_text = "(not available)"
        else:
            print(f"    Skipping — couldn't fetch enough article text from {link}", file=sys.stderr)
            return None

    task = build_article_task(title, source, article_text, instructions)
    return _call_openai(task, categories, style_examples)


def generate_custom_post(brief: str, categories: dict, style_examples: list[str]) -> dict | None:
    """From-scratch post requested directly, no article involved at
    all — the plain-message flow."""
    task = build_custom_task(brief)
    return _call_openai(task, categories, style_examples)


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


def write_post_file(post: dict, source_url: str | None = None, source_name: str | None = None) -> str:
    """source_url/source_name are omitted from the frontmatter entirely
    when absent (both are optional in content.config.ts) — a custom,
    from-scratch post has no article to attribute."""
    slug = unique_slug(slugify(post["title"]))
    pub_date = time.strftime("%Y-%m-%d")
    tags_yaml = ", ".join(f'"{t}"' for t in post["tags"])

    lines = [
        "---",
        f'title: {json.dumps(post["title"])}',
        f'description: {json.dumps(post["description"])}',
        f"pubDate: {pub_date}",
        f"tags: [{tags_yaml}]",
    ]
    if source_url:
        lines.append(f"sourceUrl: {json.dumps(source_url)}")
    if source_name:
        lines.append(f"sourceName: {json.dumps(source_name)}")
    lines += ['author: "ai"', "---", "", post["body"], ""]

    path = BLOG_DIR / f"{slug}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
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
        source_url = source_name = None

        if kind == "custom":
            preview = item["brief"] if len(item["brief"]) <= 60 else item["brief"][:59] + "…"
            print(f"  Writing custom post: \"{preview}\"...")
            post = generate_custom_post(item["brief"], categories, style_examples)
        else:
            instructions = item.get("instructions")
            suffix = f" — focus: \"{instructions}\"" if instructions else ""
            print(f"  Writing: {item['title'][:60]}...{suffix}")
            post = generate_post(
                item["title"], item["source"], item["link"], categories, style_examples, instructions
            )
            source_url, source_name = item["link"], item["source"]

        if post is None:
            continue  # leave status "pending" — will retry next run

        slug = write_post_file(post, source_url, source_name)
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
