"""
Drafting — the one place a post's prose is written.

**This is a move, not a rewrite.** The system prompt, the temperature
(0.75), the two-model split, the 850-word minimum, the 1200-word target
and the expansion second pass are carried over verbatim from
scripts/generate_blog_post.py by way of the superseded branch's
channels/news.py. Phase 2's acceptance criterion is that the refactored
research channel reproduces today's Scout decision logic, and the only
way to be sure of that is to change none of it.

What IS new, and is additive rather than a change:

  - the closed vocabulary the prompt is given comes from
    core/taxonomy.py rather than being read inline, so it follows
    taxonomy.json;
  - the section and format are decided by the classifier BEFORE
    drafting and passed in, rather than being fixed at "news";
  - `scout` provenance is threaded through to the frontmatter, because
    §4.1 rule 5 makes it required;
  - each section can prepend its own §8 post-shape rules.

DEVIATION FROM §12'S FILE LIST, DELIBERATE — see core/pipeline.py for
the same note. §12 does not name this module; without it the drafting
code would be copied into three channels.
"""

from __future__ import annotations

import sys

from . import llm as llm_module, taxonomy as tax
from .constants import BLOG_DIR
from .frontmatter import read_frontmatter

ARTICLE_MAX_CHARS = 8000
STYLE_EXAMPLE_COUNT = 2

# Length instructions alone (however forceful) reliably underperform for
# this model — it converges on ~700 words regardless. Below MIN_WORDS we
# ask it to expand the actual draft instead of just repeating "write
# more" in a fresh prompt; that is far more reliable. Carried over
# unchanged.
MIN_WORDS = 850
TARGET_WORDS = 1200


def load_style_examples(fmt: str = "news") -> list[str]:
    """Existing posts of the same SHAPE, used as few-shot style examples
    so the model matches this blog's voice instead of writing generic
    AI-blog filler.

    Selected by `format` rather than by section, which is the one place
    the three-axis model changes this function: a short timely item and
    a deep dive are different shapes wherever they are filed, and a
    Security news item should be shown Security-or-anywhere news items,
    not a 3,000-word teardown that happens to share its section.
    """
    examples = []
    for path in sorted(BLOG_DIR.glob("*.md")):
        data = read_frontmatter(path)
        if data.get("format") != fmt:
            continue
        examples.append(path.read_text(encoding="utf-8"))
        if len(examples) >= STYLE_EXAMPLE_COUNT:
            break
    return examples


def build_system_prompt(
    style_examples: list[str], *, section: str, section_rules: str = ""
) -> str:
    """Shared scaffolding (voice, style examples, topic list, JSON
    contract) — sent as the system message, with the specific task as
    the user message. Carried over verbatim except for the topic block,
    which now comes from taxonomy.json, and the section rules block,
    which is new and empty by default."""
    topic_list = tax.topic_prompt_block()
    examples_block = "\n\n---\n\n".join(style_examples) or "(no examples available)"
    rules_block = f"\n\n{section_rules.strip()}\n" if section_rules.strip() else ""

    return f"""You are writing a blog post for "securesein", an AI research
radar written by a hands-on engineer — mechanism first, from sources,
never from press releases.

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
- Any performance or benchmark figure that comes from the party that
  built the thing is a VENDOR CLAIM and must be written as one, in
  those words. Never state a vendor's number as an established fact.
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

Every factual claim, number and version string in this post must come
from the source text you are given. Do not add a figure you remember
from elsewhere, do not round one, and do not fill a gap with something
plausible. A deterministic check compares every number in your draft
against the source and rejects the post outright if one does not
appear there — there is no review step that would catch it first and
no retry.

The example posts below are for topical scope and this blog's subject
matter only — they're shorter and drier than the voice above calls
for, so don't mimic their brevity, override it:

{examples_block}{rules_block}

---

This post is being filed in the "{section}" section: {tax.sections()[section]["question"]}

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


def build_article_task(
    title: str, source: str, article_text: str, instructions: str | None = None
) -> str:
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


def _expand_body(llm, body: str, task: str, system_prompt: str) -> str | None:
    """Second pass, only used when the first draft came in under
    MIN_WORDS: asks the model to expand the existing draft (not
    rewrite from scratch). Carried over unchanged."""
    word_count = len(body.split())
    expand_task = f"""Below is a draft blog post body that came in at
{word_count} words — under the {MIN_WORDS}-word minimum. Expand it to
at least {TARGET_WORDS} words:
- add 1-2 more fully worked examples (150+ words each, concrete
  specifics — real numbers, what a user/developer sees at each step)
  to sections that currently just gesture at a point
- go deeper on an angle the draft hasn't covered yet (a failure mode,
  an implementation detail, how this is handled in practice)

Every number you add must still come from the source text. Do not
introduce a figure the source does not contain.

Do not shorten, remove, or rewrite what's already good — keep the
existing structure, voice, and throughline; only add material that
connects into it, per the STRUCTURE rule. Return the SAME JSON shape
as before (title, description, topics, body) with the expanded body.

ORIGINAL TASK (for context):
{task}

DRAFT BODY TO EXPAND:
{body}"""

    expanded = llm.json(
        expand_task,
        model=llm_module.BLOG_MODEL,
        system=system_prompt,
        temperature=0.75,
        label="expansion pass",
    )
    if expanded is None:
        print(f"    Expansion pass failed, keeping the {word_count}-word draft.",
              file=sys.stderr)
        return None
    expanded_body = str(expanded.get("body", "")).strip()
    if len(expanded_body.split()) <= word_count:
        return None  # didn't actually help — keep the original
    return expanded_body


def call_model(
    llm,
    task: str,
    *,
    section: str,
    fmt: str = "news",
    section_rules: str = "",
    fallback_topics: list[str] | None = None,
) -> dict | None:
    """Draft one post. Returns None rather than raising on every
    failure path, because a channel that cannot draft one item must
    still finish its run."""
    system_prompt = build_system_prompt(
        load_style_examples(fmt), section=section, section_rules=section_rules
    )
    data = llm.json(
        task,
        model=llm_module.BLOG_MODEL,
        system=system_prompt,
        temperature=0.75,
        label="draft",
    )
    if data is None:
        return None

    # Light fallback — never fully trust the shape of an API response,
    # even a "structured" one.
    if not data.get("title") or not data.get("body"):
        print(f"    Model response missing title/body, skipping: {data}", file=sys.stderr)
        return None

    # Unknown slugs are dropped, never coerced into something close and
    # never allowed through as a new topic.
    requested = data.get("topics") or data.get("tags") or []
    valid = tax.valid_topics(requested)
    for slug in requested:
        if slug not in valid:
            print(f"    Dropping invented topic {slug!r}.", file=sys.stderr)
    if not valid:
        # The classifier already picked topics from the closed list for
        # this item; falling back to those beats discarding a finished
        # draft over a formatting slip in the second call.
        valid = tax.valid_topics(fallback_topics)
    if not valid:
        print("    No valid topic survived — not publishing this one.", file=sys.stderr)
        return None

    body = str(data["body"]).strip()
    word_count = len(body.split())
    if word_count < MIN_WORDS:
        print(f"    Draft was {word_count} words (under {MIN_WORDS}) — expanding...",
              file=sys.stderr)
        expanded = _expand_body(llm, body, task, system_prompt)
        if expanded:
            body = expanded
            print(f"    Expanded to {len(body.split())} words.", file=sys.stderr)

    return {
        "title": str(data["title"]).strip(),
        "description": str(data.get("description", "")).strip() or "Read more below.",
        "topics": valid,
        "body": body,
    }
