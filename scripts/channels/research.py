"""
The Research channel — "What have we learned?" (brief §8.3).

Broader than papers. **Mechanism over event**: a piece explaining *how*
something works outranks one reporting *that* it happened, which is what
`depth_bonus` in the relevance rank is for.

Three §8.3 rules, all enforced in code rather than asked for in a prompt:

  - A paper alone is rarely enough. Papers with released code, a
    reproduction or a well-argued critique attached score higher, via
    the verifiability component of the quality gate.
  - **Never publish a post whose only source is another roundup.**
    Import AI, TLDR AI, HF Daily Papers and the rest are discovery aids;
    the pipeline follows them to the primary source or drops the item.
    This is a hard reject, not a score penalty, because a score penalty
    is something a quiet week can overcome.
  - Replication failures, contamination findings and negative results
    are first-class Research material and routinely more useful than
    positive ones. They are given an explicit lift in the section rules
    the drafter is handed, and they are what `evaluation` exists for as
    a topic.

This channel also carries the LEGACY MARKED-ITEM PATH — the Telegram
reply-to-an-article flow that is how Scout has actually been publishing
since before any of this. That path is a MOVE, not a rewrite: the same
marked.json contract, the same duplicate checks in the same order, the
same relevance gate, the same drafting call. What changed is that the
section is now classified rather than hard-coded to "news", the ledger
is consulted before the expensive drafting call, and --dry-run decides
everything and writes nothing.

    python scripts/run.py --channel research [--dry-run]
"""

from __future__ import annotations

import json
import sys
import time

from core import draft as draft_module, pipeline
from core.constants import (
    BLOG_DIR,
    DATA_DIR,
    FEEDS_NEWS_FILE,
    FEEDS_RESEARCH_SECURITY_FILE,
)
from core.dedup import is_duplicate
from core.frontmatter import existing_posts
from core.profile import ROUNDUP_SOURCES, profile as load_profile_object
from core.state import reject

CHANNEL = "research"
SECTION = "research"
# Research reads the research/security file and the original news feeds:
# the latter is where the lab blogs, the individual writers and the
# arXiv categories already live, and §14.1g is explicit that those rows
# exist in the new files for TIERING, not for a second fetch of the same
# URL.
SOURCE_FILES = (FEEDS_RESEARCH_SECURITY_FILE, FEEDS_NEWS_FILE)

MARKED_FILE = DATA_DIR / "marked.json"

# Handed to the drafter as extra system-prompt material. Section rules
# belong here rather than in core/draft.py so that what makes Research
# different from Security is one readable block in one file.
SECTION_RULES = """SECTION RULES — Research:
- Mechanism over event. The post's job is to explain HOW the thing
  works, not to report THAT it happened. If you find yourself writing a
  timeline, you have the wrong angle.
- A negative result, a replication failure or a contamination finding
  is first-class material and usually more useful than a positive
  result. Write it with the same weight, not as a caveat.
- Say what would have to be true for the finding to be wrong, and what
  the paper does not show. A limitations paragraph is not a hedge.
- If the work has released code, a reproduction or a serious critique
  attached, say so and say where."""


def _roundup_only(item) -> str | None:
    """§8.3's hard rule. A roundup names the primary source in its own
    text; the pipeline is supposed to follow that link, not summarise
    the summary."""
    if item.source.name in ROUNDUP_SOURCES:
        return "roundup_only_source"
    return None


# ---------------------------------------------------------------------
# The feed path
# ---------------------------------------------------------------------


def run_feeds(ctx) -> int:
    outcome = pipeline.run_flow(
        ctx,
        channel=CHANNEL,
        sections=(SECTION,),
        source_files=SOURCE_FILES,
        section_hint=SECTION,
        extra_reject=_roundup_only,
    )

    prof = load_profile_object()
    stats = pipeline.gate_stats(outcome.scores, prof)
    if stats.get("n"):
        print(f"  quality gate: {stats['passed']}/{stats['n']} passed "
              f"({stats['pass_rate']:.0%}), median {stats['median']}, "
              f"p75 {stats['p75']}, p90 {stats['p90']}, threshold {stats['threshold']}")

    return pipeline.publish_ranked(
        ctx, outcome, channel=CHANNEL, section=SECTION, section_rules=SECTION_RULES
    )


# ---------------------------------------------------------------------
# The legacy marked-item path (Telegram reply -> post)
# ---------------------------------------------------------------------


def load_marked() -> dict:
    if not MARKED_FILE.exists():
        return {}
    with open(MARKED_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_marked(marked: dict, dry_run: bool) -> None:
    if dry_run:
        return
    with open(MARKED_FILE, "w", encoding="utf-8") as f:
        json.dump(marked, f, ensure_ascii=False, indent=2)


def run_marked(ctx) -> int:
    """Items the owner replied to in Telegram. Carried over from
    generate_blog_post.py with its control flow intact — see the module
    docstring for exactly what changed and why."""
    from core import classify
    from core.feeds import Item, Source, fetch_article_text

    llm, dry_run = ctx.llm, ctx.dry_run
    marked = load_marked()
    existing = existing_posts()
    pending = {sid: i for sid, i in marked.items() if i.get("status") == "pending"}
    print(f"  {len(pending)} marked item(s) pending a post.")
    published = 0

    for sid, entry in pending.items():
        title = entry.get("title", "(custom)")
        # The ledger comes before the expensive drafting call, not after:
        # a section at its target stops drafting entirely rather than
        # drafting and discarding.
        verdict = ctx.ledger.can_publish(SECTION, published)
        if not verdict:
            ctx.ledger.refuse(CHANNEL, verdict, title=title, score=None)
            # Status stays "pending": this item is fine, there was just
            # no room for it. It gets another go next run.
            continue

        if entry.get("kind") == "custom":
            preview = entry["brief"][:59] + "…" if len(entry["brief"]) > 60 else entry["brief"]
            print(f'  Writing custom post: "{preview}"...')
            drafted = draft_module.call_model(
                llm,
                draft_module.build_custom_task(entry["brief"]),
                section=SECTION,
                fmt="explainer",
                section_rules=SECTION_RULES,
            )
            source_url = source_name = None
            section, fmt = SECTION, "explainer"
            topics = drafted["topics"] if drafted else []
        else:
            if is_duplicate(title, entry.get("link"), existing):
                reject(CHANNEL, "duplicate_url", title=title,
                       url=entry.get("link", ""), dry_run=dry_run)
                marked[sid].update(status="skipped", skipped_reason="duplicate")
                save_marked(marked, dry_run)
                continue

            source_url, source_name = entry["link"], entry["source"]
            article_text = fetch_article_text(source_url, draft_module.ARTICLE_MAX_CHARS)
            if len(article_text) < 200 and not entry.get("instructions"):
                print(f"    Skipping — couldn't fetch enough article text from "
                      f"{source_url}", file=sys.stderr)
                continue

            # The section is classified now rather than fixed at "news",
            # which is the one behavioural change on this path: a
            # marked item about a jailbreak files itself under Security.
            item = Item(id=sid, title=title, url=source_url,
                        source=Source(name=source_name, url=source_url),
                        summary=article_text[:2000])
            axes = classify.classify_axes(llm, item)
            section, fmt, topics = axes["section"], axes["format"], axes["topics"]

            instructions = entry.get("instructions")
            suffix = f' — focus: "{instructions}"' if instructions else ""
            print(f"  Writing: {title[:60]}...{suffix} -> {section}")
            drafted = draft_module.call_model(
                llm,
                draft_module.build_article_task(
                    title, source_name, article_text or "(not available)", instructions
                ),
                section=section,
                fmt=fmt,
                section_rules=SECTION_RULES,
                fallback_topics=topics,
            )

        if drafted is None:
            continue  # leave status "pending" — will retry next run

        # Second duplicate pass, on the DRAFTED headline: two feeds can
        # carry one story under different words and converge once a
        # model has rewritten both.
        if source_url and is_duplicate(drafted["title"], None, existing):
            reject(CHANNEL, "duplicate_title", title=drafted["title"], dry_run=dry_run)
            marked[sid].update(status="skipped",
                               skipped_reason="duplicate after drafting")
            save_marked(marked, dry_run)
            continue

        slug = _write_marked(ctx, drafted, section, fmt, source_url, source_name, sid)
        published += 1
        existing.append({
            "slug": slug, "title": drafted["title"],
            "pub_date": time.strftime("%Y-%m-%d"), "kind": section,
            "format": fmt, "topics": drafted["topics"],
            "source_url": source_url or "", "path": BLOG_DIR / f"{slug}.md",
        })
        marked[sid].update(status="published", slug=slug, published_at=time.time())
        save_marked(marked, dry_run)  # after each post, not just at the end

    return published


def _write_marked(ctx, drafted, section, fmt, source_url, source_name, sid) -> str:
    from core import llm as llm_module
    from core.frontmatter import render, slugify, write_post

    scout = {
        "qualityScore": 100.0,
        "relevanceScore": 100.0,
        # A directed request is its own reason, and saying so is more
        # honest than synthesising a profile-match sentence for an item
        # the owner picked by hand.
        "whyRelevant": "Requested directly by the site owner via Telegram.",
        "candidateId": f"marked:{sid}",
    }
    text = render(drafted, kind=section, fmt=fmt, model=llm_module.BLOG_MODEL,
                  source_url=source_url, source_name=source_name, scout=scout)
    if ctx.dry_run:
        slug = slugify(drafted["title"])
        print(f"    [dry-run] would write src/content/blog/{slug}.md "
              f"({len(drafted['body'].split())} words)")
    else:
        slug = write_post(text, drafted["title"])
        print(f"    -> src/content/blog/{slug}.md")
    ctx.ledger.record(slug, CHANNEL, section,
                      quality=scout["qualityScore"], relevance=scout["relevanceScore"])
    return slug


def run(ctx) -> int:
    published = run_marked(ctx)
    published += run_feeds(ctx)
    print("Done.")
    return published
