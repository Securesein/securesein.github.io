"""
Turn a marked news item into a full English blog post and write it as
a new Markdown file in src/content/blog/, matching the Astro content
schema exactly (see src/content.config.ts).

Scout's half of that schema is fixed and non-negotiable:

    kind:   always "news"
    credit: always "scout"
    source: always present — url + publisher
    model:  the model that actually drafted it
    topics: 1-3 slugs from the CLOSED list in /taxonomy.json

Scout must never emit kind "explainer" or "deepdive", and never a
credit other than "scout". Those lanes are not human-*written* — a
model drafts them too — but they are human-*directed*, and only
Sebastiaan can assert that. A pipeline claiming credit "directed"
would make every credit line on the site worthless.

Because Scout publishes without review, the schema is the only quality
gate that exists, so this script also enforces three of its own before
spending a drafting call: a relevance gate, a duplicate check against
the existing archive, and a topic parse that drops unknown slugs
rather than inventing them.

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

Every post is published automatically, with credit "scout" — no draft
/ review step. Git is the safety net (a bad post is a `git revert` away),
matching the "geparkeerd voor later" decision in the project brief to
skip a manual approval step.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from openai import OpenAI

from article_fetch import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MARKED_FILE = DATA_DIR / "marked.json"
BLOG_DIR = REPO_ROOT / "src" / "content" / "blog"
TAXONOMY_FILE = REPO_ROOT / "taxonomy.json"

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
# Deliberately a stronger (and pricier) model than the Telegram summary
# step — this is the one piece of writing that actually gets published.
BLOG_MODEL = os.environ.get("OPENAI_BLOG_MODEL", "gpt-4o")

ARTICLE_MAX_CHARS = 8000
STYLE_EXAMPLE_COUNT = 2

# Cheap model for the yes/no gates — they classify, they don't write.
GATE_MODEL = os.environ.get("OPENAI_GATE_MODEL", "gpt-4o-mini")

# Duplicate detection window. The three near-identical GPT-6 Astra posts
# on 4, 5 and 6 September are what this exists to prevent.
DEDUP_DAYS = 7
# Two title-overlap rules, because one threshold cannot cover both
# shapes this failure takes. A few shared words in a short headline is
# strong evidence ("GPT-6 Astra" twice); a handful of shared words in
# two long headlines is weaker per word but adds up. Tuned against the
# three real GPT-6 Astra posts, which all three get caught by, and
# against every other pair in the archive, which none of them do.
DEDUP_RULES = (
    # (minimum shared distinctive words, minimum containment)
    (3, 0.40),
    (2, 0.50),
)
DEDUP_SEQUENCE_RATIO = 0.72

TITLE_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for",
    "from", "how", "in", "into", "is", "it", "its", "new", "of", "on", "or",
    "s", "that", "the", "their", "this", "to", "what", "when", "who", "why",
    "will", "with", "you", "your", "inside", "exploring", "understanding",
    "unpacking", "navigating", "introducing", "look", "closer", "era",
}

# Length instructions alone (however forceful) reliably underperform
# for this model — it converges on ~700 words regardless. Below
# MIN_WORDS, we ask it to expand the actual draft instead of just
# repeating "write more" in a fresh prompt; that's far more reliable.
MIN_WORDS = 850
TARGET_WORDS = 1200

client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Inputs: taxonomy, existing archive, style examples
# ---------------------------------------------------------------------------

def load_topics() -> dict:
    """The closed topic vocabulary, read from the same /taxonomy.json
    the Astro side reads (src/taxonomy.ts) so the two can never drift.
    The build fails on an unknown topic, which is the point: an open
    vocabulary rots within a month once a pipeline starts inventing
    slugs."""
    with open(TAXONOMY_FILE, encoding="utf-8") as f:
        return json.load(f)["topics"]


def _frontmatter(path: Path) -> dict:
    """Enough of a YAML reader for the handful of flat scalar fields
    this script needs. Deliberately not a dependency — the pipeline
    installs from scripts/requirements.txt and this is not worth a
    wheel."""
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


def load_existing_posts() -> list[dict]:
    """Title, date and source URL of everything already published —
    the input to the duplicate check."""
    posts = []
    for path in sorted(BLOG_DIR.glob("*.md")):
        data = _frontmatter(path)
        if not data.get("title"):
            continue
        posts.append({
            "slug": path.stem,
            "title": data["title"],
            "pub_date": data.get("pubDate", ""),
            "kind": data.get("kind", "news"),
            "source_url": (data.get("source") or {}).get("url", ""),
            "path": path,
        })
    return posts


def load_style_examples() -> list[str]:
    """Existing News posts, used as few-shot style examples so the
    model matches this blog's voice instead of writing generic AI-blog
    filler. Only News: the Fundamentals and Deep dive posts are longer
    and differently shaped, and Scout is not writing those."""
    examples = []
    for path in sorted(BLOG_DIR.glob("*.md")):
        if _frontmatter(path).get("kind") != "news":
            continue
        examples.append(path.read_text(encoding="utf-8"))
        if len(examples) >= STYLE_EXAMPLE_COUNT:
            break
    return examples


# ---------------------------------------------------------------------------
# Gate 1: is this even a story?
# ---------------------------------------------------------------------------

REJECT_REASONS = {
    "about_publication": "it is about a publication or its staff, not a story",
    "funding_only": "it is a funding or corporate item with no product angle",
    "press_release": "it is a press release with no technical substance",
}


# Words that turn "the publisher's own name is in the headline" from a
# coincidence into a story about the publisher. Deliberately narrow:
# a vendor blog writing about its own product ("Google's August AI
# announcements") is exactly what this site is for, and must not trip.
NEWSROOM_WORDS = (
    "names", "appoints", "hires", "joins", "editor", "editorial", "analyst",
    "newsroom", "columnist", "coverage", "subscribers", "newsletter",
    "masthead", "staff", "role", "relaunch", "redesign", "acquires us",
)


def _publication_self_reference(title: str, source: str) -> bool:
    """Catches the exact failure already in the archive: "Understanding
    VentureBeat's Role in the AI Industry", written from a VentureBeat
    post about VentureBeat hiring its first lead analyst.

    Requires both signals — the publisher's name in the headline *and* a
    word about the business of publishing. The name alone is not enough:
    half this blog's sources are vendor blogs, and "Google's August AI
    Announcements" from the Google AI Blog is a real story."""
    words = re.findall(r"[a-z]+", source.lower())
    stop = {"ai", "blog", "news", "the", "weblog", "technical", "engineering", "at"}
    names = [w for w in words if w not in stop and len(w) > 3]
    haystack = title.lower()
    if not any(name in haystack for name in names):
        return False
    return any(word in haystack for word in NEWSROOM_WORDS)


def passes_relevance_gate(title: str, source: str, article_text: str) -> bool:
    """Scout publishes without review, so the only thing standing
    between a non-story and the front page is this. Rejects the three
    shapes that have actually gone wrong or obviously would."""
    if _publication_self_reference(title, source):
        print(f"    Rejected — {REJECT_REASONS['about_publication']} "
              f"(publisher's own name plus newsroom language in the headline).",
              file=sys.stderr)
        return False

    prompt = f"""Decide whether this item is worth a technical blog post
for an audience of developers, IT/sysadmins and enterprise architects.

REJECT it if any of these is true:
- It is about a publication, a website, a conference or a person's job
  title, rather than about technology. A publisher writing about its
  own analysts, hires, or editorial strategy is always a reject.
- It is a funding round, valuation, or corporate reshuffle with no
  product or technical angle a reader could act on.
- It is a press release or marketing announcement with no technical
  substance — no mechanism, no numbers, no shipped capability.

ACCEPT it if there is something a technical reader could learn: a
capability that shipped, how something works, what broke, what it
costs, or a concrete change to a tool they use.

TITLE: {title}
PUBLISHER: {source}
ARTICLE (truncated):
{article_text[:3000]}

Return ONLY JSON: {{"publish": true|false, "reason": "one short sentence"}}"""

    try:
        response = client.chat.completions.create(
            model=GATE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        verdict = json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        # A gate that fails closed would silently stop the whole
        # pipeline on an API blip; a gate that fails open only risks
        # one weak post, which git can revert.
        print(f"    Relevance gate errored, letting it through: {e}", file=sys.stderr)
        return True

    if not verdict.get("publish", True):
        print(f"    Rejected — {verdict.get('reason', 'no reason given')}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# Gate 2: have we already covered this?
# ---------------------------------------------------------------------------

def _title_tokens(title: str) -> set[str]:
    """Distinctive words only. Single digits are kept deliberately —
    the "6" in "GPT-6 Astra" carries more of the story's identity than
    any other token in that headline."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {
        w for w in words
        if w not in TITLE_STOPWORDS and (len(w) > 1 or w.isdigit())
    }


def _same_story(a: str, b: str) -> bool:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if ta and tb:
        shared = len(ta & tb)
        containment = shared / min(len(ta), len(tb))
        for min_shared, min_containment in DEDUP_RULES:
            if shared >= min_shared and containment >= min_containment:
                return True
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= DEDUP_SEQUENCE_RATIO


def _recent(posts: list[dict]) -> list[dict]:
    cutoff = date.today() - timedelta(days=DEDUP_DAYS)
    recent = []
    for post in posts:
        try:
            pub = date.fromisoformat(post["pub_date"][:10])
        except ValueError:
            continue
        if pub >= cutoff:
            recent.append(post)
    return recent


def is_duplicate(title: str, link: str | None, existing: list[dict]) -> bool:
    """Two checks, in cost order. A shared source URL is definitive at
    any age — the same article is never worth two posts. Title
    similarity only applies inside a 7-day window, because the same
    words a week apart are usually a duplicate and the same words a
    year apart usually are not."""
    if link:
        for post in existing:
            if post["source_url"] and post["source_url"] == link:
                print(f"    Skipping — already covered in {post['slug']} "
                      f"(same source URL).", file=sys.stderr)
                return True

    for post in _recent(existing):
        if _same_story(title, post["title"]):
            print(f"    Skipping — too close to {post['slug']} "
                  f"(\"{post['title']}\"), published {post['pub_date']}.",
                  file=sys.stderr)
            return True
    return False


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def build_system_prompt(topics: dict, style_examples: list[str]) -> str:
    """Shared scaffolding (voice, style examples, topic list, JSON
    contract) — sent as the system message, with the specific task
    (see build_article_task() etc.) as the user message. Splitting
    them this way, instead of one long user message, makes the model
    noticeably more likely to actually follow the hard constraints
    below (length, structure) rather than treating them as background
    color."""
    topic_list = "\n".join(
        f'- "{slug}": {info["label"]} — {info["description"]}'
        for slug, info in topics.items()
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

TOPICS — this list is CLOSED. Pick 1, or up to 3 if they genuinely all
apply. Use the exact slug, in quotes, and nothing else. Do NOT invent a
slug, do NOT return a label instead of a slug, and do NOT return a topic
that is merely adjacent to the story. Anything not on this list is
discarded, and a post with no valid topic left is not published at all:
{topic_list}

Return ONLY a JSON object with exactly these keys, nothing else:
{{
  "title": "a clear, specific headline for the post",
  "description": "one sentence, shown under the title as a lede",
  "topics": ["one-to-three-slugs-from-the-closed-list-above"],
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
as before (title, description, topics, body) with the expanded body.

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


def _call_openai(task: str, topics: dict, style_examples: list[str]) -> dict | None:
    system_prompt = build_system_prompt(topics, style_examples)
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

    # Unknown slugs are dropped, never coerced into something close and
    # never allowed through as a new topic. If nothing survives, the
    # model did not understand the story well enough to file it, and an
    # unfiled post would fail the build anyway.
    requested = data.get("topics") or data.get("tags") or []
    valid_topics = []
    for slug in requested:
        if slug in topics and slug not in valid_topics:
            valid_topics.append(slug)
        elif slug not in topics:
            print(f"    Dropping invented topic {slug!r}.", file=sys.stderr)
    valid_topics = valid_topics[:3]
    if not valid_topics:
        print("    No valid topic survived — not publishing this one.", file=sys.stderr)
        return None

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
        "topics": valid_topics,
        "body": body,
    }


def generate_post(
    title: str, source: str, link: str, topics: dict, style_examples: list[str],
    instructions: str | None = None, gate: bool = True,
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

    # Relevance is judged from the article, so this runs after the
    # fetch but before the expensive drafting call. Skipped when the
    # user attached instructions: he has looked at the item and asked
    # for it, which outranks the gate's opinion.
    if gate and not instructions and not passes_relevance_gate(title, source, article_text):
        return None

    task = build_article_task(title, source, article_text, instructions)
    return _call_openai(task, topics, style_examples)


def generate_custom_post(brief: str, topics: dict, style_examples: list[str]) -> dict | None:
    """From-scratch post requested directly, no article involved at
    all — the plain-message flow. No relevance gate and no duplicate
    check: he asked for this one in so many words."""
    task = build_custom_task(brief)
    return _call_openai(task, topics, style_examples)


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
    """Writes Scout's half of the schema, which is fixed: kind "news",
    credit "scout", the drafting model named, and a `source` object
    whenever there is an article behind the post.

    `source` is omitted only for the custom, from-scratch flow, which
    genuinely has no article to attribute. The schema hard-fails a
    Scout post without a source from the migration cutover onward, so
    that path is the one thing here that can legitimately break the
    build — which is correct: a sourceless news item should not ship
    silently."""
    slug = unique_slug(slugify(post["title"]))
    pub_date = time.strftime("%Y-%m-%d")
    topics_yaml = ", ".join(f'"{t}"' for t in post["topics"])

    lines = [
        "---",
        f'title: {json.dumps(post["title"])}',
        f'description: {json.dumps(post["description"])}',
        f"pubDate: {pub_date}",
        # Never anything but these two. Scout cannot assert that a post
        # was human-directed, and a pipeline that claimed it could would
        # make every credit line on the site worthless.
        'kind: "news"',
        f"topics: [{topics_yaml}]",
        'credit: "scout"',
        f"model: {json.dumps(BLOG_MODEL)}",
    ]
    if source_url:
        lines.append("source:")
        lines.append(f"  url: {json.dumps(source_url)}")
        lines.append(f"  publisher: {json.dumps(source_name or 'Unknown')}")
    lines += ["---", "", post["body"], ""]

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
    topics = load_topics()
    style_examples = load_style_examples()
    existing = load_existing_posts()
    marked = load_marked()

    pending = {sid: item for sid, item in marked.items() if item.get("status") == "pending"}
    print(f"{len(pending)} item(s) pending a blog post.")

    for sid, item in pending.items():
        kind = item.get("kind", "article")
        source_url = source_name = None

        if kind == "custom":
            preview = item["brief"] if len(item["brief"]) <= 60 else item["brief"][:59] + "…"
            print(f"  Writing custom post: \"{preview}\"...")
            post = generate_custom_post(item["brief"], topics, style_examples)
        else:
            instructions = item.get("instructions")

            # Cheapest gate first: a duplicate costs nothing to detect
            # and everything to publish.
            if is_duplicate(item["title"], item.get("link"), existing):
                marked[sid]["status"] = "skipped"
                marked[sid]["skipped_reason"] = "duplicate"
                save_marked(marked)
                continue

            suffix = f" — focus: \"{instructions}\"" if instructions else ""
            print(f"  Writing: {item['title'][:60]}...{suffix}")
            post = generate_post(
                item["title"], item["source"], item["link"], topics, style_examples, instructions
            )
            source_url, source_name = item["link"], item["source"]

        if post is None:
            continue  # leave status "pending" — will retry next run

        # Second duplicate pass, on the *drafted* headline: two feeds
        # can carry the same story under different words and converge
        # once a model has rewritten both.
        if kind != "custom" and is_duplicate(post["title"], None, existing):
            marked[sid]["status"] = "skipped"
            marked[sid]["skipped_reason"] = "duplicate after drafting"
            save_marked(marked)
            continue

        slug = write_post_file(post, source_url, source_name)
        print(f"    -> src/content/blog/{slug}.md")

        # Keep the in-memory archive current so two items in the same
        # run cannot duplicate each other.
        existing.append({
            "slug": slug,
            "title": post["title"],
            "pub_date": time.strftime("%Y-%m-%d"),
            "kind": "news",
            "source_url": source_url or "",
            "path": BLOG_DIR / f"{slug}.md",
        })

        marked[sid]["status"] = "published"
        marked[sid]["slug"] = slug
        marked[sid]["published_at"] = time.time()
        save_marked(marked)  # save after each post, not just at the end

    print("Done.")


def run_test(url: str) -> None:
    """Generates one post from an arbitrary URL, independent of
    data/marked.json — for checking output quality/format first."""
    topics = load_topics()
    style_examples = load_style_examples()
    print(f"Style examples loaded: {len(style_examples)}")

    # gate=False: --test is for checking output quality on a URL you
    # already chose, so the relevance gate would only get in the way.
    post = generate_post("(test article)", "Test source", url, topics, style_examples, gate=False)
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
