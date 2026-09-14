"""
The shared candidate flow (brief §7), used by every post-writing channel.

    feeds
      -> ingestion            per-source adapters, failure-isolated
      -> deduplication        url -> title -> entity
      -> exclusion filter     interest_profile exclude[] — hard drop
      -> classification       section, format, topics (closed enums)
      -> quality gate         pass/fail, threshold from the profile
      -> relevance ranking    orders the queue, never opens it
      -> budget check
      -> publish (top N)  |  radar (the rest)
      -> verification gates
      -> commit

DEVIATION FROM §12'S FILE LIST, DELIBERATE. The brief's repo layout does
not name a pipeline module; it lists per-channel modules under
scripts/channels/. Written that way, the ingest-dedup-exclude-classify-
gate-rank-budget sequence would be copied three times and would drift
three ways within a month — and the §16 principle is "simple > clever"
and "this must stay debuggable by one person on a weekend". So the
sequence lives here once, and a channel is a small declaration of what
makes it different: which feed files it reads, which section it
publishes into, its §8 rules, and how it drafts.

WHAT A DRY RUN WRITES. Everything observable and nothing consequential:
state/queue.json, state/rejected.jsonl, state/unresolved_models.jsonl,
state/topic_activity.json and the radar collection are written; post
files, the ledger and the entity cooldowns are not. That asymmetry is
the whole point — the thresholds are tuned from what a dry run leaves
behind, so a dry run that left nothing behind would be useless.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from . import classify, taxonomy as tax
from .dedup import is_duplicate
from .feeds import Item, Source, fetch, load_sources
from .frontmatter import existing_posts
from .profile import (
    Profile,
    QualityScore,
    RelevanceScore,
    TopicActivity,
    excluded,
    profile as load_profile_object,
    quality_gate,
    quality_gate_offline,
    relevance_rank,
    why_relevant,
)
from .constants import seen_items_file
from .radar import Radar, radar_id
from .state import read_json, reject, write_json


@dataclass
class Candidate:
    item: Item
    section: str = ""
    format: str = "news"
    topics: list[str] = field(default_factory=list)
    quality: QualityScore | None = None
    relevance: RelevanceScore | None = None
    why: str = ""

    @property
    def id(self) -> str:
        return radar_id(self.item.url, self.item.title)

    @property
    def score(self) -> float:
        return self.relevance.total if self.relevance else 0.0


@dataclass
class Outcome:
    """What one run of the shared flow produced, before the channel
    decides what to do with the winners."""

    ranked: list[Candidate] = field(default_factory=list)
    radared: list[Candidate] = field(default_factory=list)
    seen: int = 0
    excluded: int = 0
    duplicates: int = 0
    gate_failed: int = 0
    scores: list[float] = field(default_factory=list)
    first_run: bool = False


def ingest(source_files, *, limit: int | None = None) -> list[Item]:
    """Every in-scope source in every named feed file, failure-isolated.

    `inScope: false` entries are skipped here rather than filtered
    downstream, so an out-of-scope source is never fetched at all — the
    decision is visible in the feed file and costs nothing at runtime.
    """
    items: list[Item] = []
    for path in source_files:
        if not path.exists():
            print(f"  {path.name}: not found — skipped.", file=sys.stderr)
            continue
        sources = load_sources(path)
        in_scope = [s for s in sources if s.in_scope]
        skipped = len(sources) - len(in_scope)
        print(f"  {path.name}: {len(in_scope)} source(s)"
              + (f", {skipped} marked inScope:false" if skipped else ""))
        for source in in_scope:
            fetched = fetch(source, limit=limit or 30)
            items.extend(fetched)
    return items


def _seen(channel: str) -> tuple[set[str], bool]:
    """(already-seen item ids, is_first_run).

    Added after the Phase 3 dry run, which showed the cost of not having
    it: the research and security channels each scored ~780 items on
    every invocation, and would have re-scored the same ~780 four hours
    later. arXiv cs.AI alone hands back 270 entries per fetch whether
    they are an hour or a month old.

    The first run has no baseline, so everything currently visible would
    read as new. It records a baseline and scores nothing — the same
    protection the Releases channel already had, for the same reason.
    """
    path = seen_items_file(channel)
    if not path.exists():
        return set(), True
    return set(read_json(path, {"ids": []})["ids"]), False


def _remember(channel: str, ids: set[str], dry_run: bool) -> None:
    """Written in a dry run too, deliberately: this is a CURSOR, not a
    publication record, the same category as queue.json. Holding it back
    would make every dry run a first run and would never show what a
    SECOND run looks like — which is the only thing a calibration week
    actually measures."""
    write_json(seen_items_file(channel), {"ids": sorted(ids)[-40000:]})


def run_flow(
    ctx,
    *,
    channel: str,
    sections: tuple[str, ...],
    source_files,
    extra_reject=None,
) -> Outcome:
    """Ingest through ranking, for a channel that owns one or more
    sections.

    The channel does NOT influence classification — see the note in
    core/classify.deterministic_axes. Items classified into a section
    this channel does not own are not dropped either: they go to the
    Radar, because the channel that does own that section will meet the
    same item on its own run, and an item silently discarded because the
    wrong channel saw it first is exactly the loss the Radar exists to
    prevent.
    """
    llm, dry_run = ctx.llm, ctx.dry_run
    prof: Profile = load_profile_object()
    archive = existing_posts()
    activity = TopicActivity.from_archive(prof, archive)
    radar: Radar = ctx.radar

    outcome = Outcome()
    fetched = ingest(source_files, limit=ctx.limit)
    seen, first_run = _seen(channel)
    everything = set(seen) | {i.id for i in fetched}
    items = [i for i in fetched if i.id not in seen]
    _remember(channel, everything, dry_run)
    outcome.first_run = first_run

    outcome.seen = len(items)
    if first_run:
        # A first run SCORES everything currently visible and PUBLISHES
        # nothing. Both halves matter and they are usually conflated.
        #
        # Publishing nothing, because everything a feed happens to be
        # showing on the day the pipeline is switched on is not news —
        # it is a month of arXiv, and a budget of two per run would work
        # through it two at a time for a fortnight.
        #
        # Scoring everything, because the Radar is retention rather than
        # a queue: those items are exactly the back catalogue a later
        # deep dive is drawn from, they cost one cheap classification
        # each, and a first run that scored nothing would leave the
        # calibration pass with an empty distribution to tune against.
        # They stay on the Radar and stay eligible for promotion.
        print(f"  FIRST RUN: {len(items)} item(s) will be scored onto the "
              f"Radar; nothing will be published or queued.")
    else:
        print(f"  {len(fetched)} fetched, {len(items)} new since the last run.")

    for item in items:
        # 1. dedup — cheapest first. A duplicate costs nothing to
        #    detect and everything to publish.
        if is_duplicate(item.title, item.url, archive):
            reject(channel, "duplicate_url", title=item.title, url=item.url,
                   dry_run=dry_run)
            outcome.duplicates += 1
            continue

        # 2. exclusion filter — a HARD DROP before any scoring. The
        #    owner said in advance not to look at this kind of thing;
        #    scoring it anyway and then discarding it would put a
        #    quality number on something that was never in question.
        fired = excluded(item.title, item.summary, item.source.name, prof)
        if fired:
            reject(channel, "profile_excluded", title=item.title, url=item.url,
                   detail=fired, dry_run=dry_run)
            outcome.excluded += 1
            continue

        # 3. channel-specific rejection (§8 rules that must run before
        #    any spend — e.g. a non-primary source cannot trigger a
        #    release).
        if extra_reject:
            reason = extra_reject(item)
            if reason:
                reject(channel, reason, title=item.title, url=item.url,
                       dry_run=dry_run)
                continue

        # 4. classification into the three closed vocabularies.
        axes = classify.classify_axes(llm, item)
        candidate = Candidate(
            item=item,
            section=axes["section"],
            format=axes["format"],
            topics=axes["topics"],
        )
        if not candidate.topics:
            reject(channel, "no_valid_topic", title=item.title, url=item.url,
                   dry_run=dry_run)
            continue

        # 5. STAGE 1 — the quality gate. Pass/fail. Below the threshold
        #    the item never reaches ranking, whatever the topic.
        candidate.quality = (
            quality_gate_offline(item, prof) if llm.offline
            else quality_gate(llm, item, prof)
        )
        outcome.scores.append(candidate.quality.total)
        if not candidate.quality.passed:
            reject(channel, "below_quality_gate", title=item.title, url=item.url,
                   score=candidate.quality.total,
                   detail=candidate.quality.components, dry_run=dry_run)
            outcome.gate_failed += 1
            continue

        # 6. STAGE 2 — relevance rank. Applied only to survivors, and it
        #    only ORDERS the queue.
        candidate.relevance = relevance_rank(
            item, candidate.section, candidate.topics, prof,
            starvation_bonus=activity.bonus(candidate.topics),
        )
        candidate.why = why_relevant(
            llm, item, candidate.section, candidate.topics, candidate.relevance, prof
        )

        # 7. Everything that passed the gate lands on the Radar. The
        #    winners are promoted out of it when they are published;
        #    §6 is explicit that nothing good is thrown away.
        radar.add(
            url=item.url,
            title=item.title,
            source=item.source.name,
            section=candidate.section,
            topics=candidate.topics,
            quality=candidate.quality.total,
            relevance=candidate.relevance.total,
            why=candidate.why,
            # seenAt is when SCOUT saw it, deliberately not when the
            # source published it. Using the article's own date put
            # Lil'Log posts from 2021 into a 2021 Radar file and
            # scattered 286 items across 24 monthly files, none of which
            # answered the question the digest actually asks: what came
            # past today.
        )

        if candidate.section in sections:
            outcome.ranked.append(candidate)
        else:
            outcome.radared.append(candidate)

    outcome.ranked.sort(key=lambda c: c.score, reverse=True)
    activity.save(dry_run)

    if first_run:
        # Everything scored is on the Radar; nothing is a candidate.
        outcome.radared.extend(outcome.ranked)
        outcome.ranked = []

    print(
        f"  {outcome.seen} seen · {outcome.duplicates} duplicate · "
        f"{outcome.excluded} excluded · {outcome.gate_failed} failed the gate · "
        f"{len(outcome.ranked)} ranked for this channel · "
        f"{len(outcome.radared)} to Radar for another section"
    )
    return outcome


def gate_stats(scores: list[float], prof: Profile) -> dict:
    """The quality-gate pass rate and score distribution — the two
    numbers Phase 3 is graded on, and the only ones that make a
    threshold tunable rather than guessed."""
    if not scores:
        return {"n": 0}
    ordered = sorted(scores)
    minimum = prof.quality_minimum

    def pct(p: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        index = p * (len(ordered) - 1)
        low, high = int(index), min(int(index) + 1, len(ordered) - 1)
        return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 1)

    passed = sum(1 for s in scores if s >= minimum)
    return {
        "n": len(scores),
        "threshold": minimum,
        "passed": passed,
        "pass_rate": round(passed / len(scores), 3),
        "min": ordered[0],
        "p25": pct(0.25),
        "median": pct(0.5),
        "p75": pct(0.75),
        "p90": pct(0.90),
        "max": ordered[-1],
    }


# ===================================================================
# Publication: draft -> verification gates -> file
# ===================================================================

from . import draft as draft_module, llm as llm_module  # noqa: E402
from .feeds import fetch_article_text  # noqa: E402
from .frontmatter import render, write_post  # noqa: E402
from .registry import load_registry  # noqa: E402
from .verify import (  # noqa: E402
    g1_numeric_grounding,
    g2_entity_grounding,
    g2_models_resolve,
    g3_verifier,
    g5_reference_integrity,
)

GATE_REASONS = {
    "G1": "gate_g1_ungrounded_number",
    "G2": "gate_g2_entity_not_in_source",
    "G3": "gate_g3_verifier_rejected",
    "G5": "gate_g5_dangling_reference",
}


def run_gates(
    llm,
    draft: dict,
    source_text: str,
    *,
    release: dict | None = None,
    model_names: list[str] | None = None,
    benchmark_refs: list[str] | None = None,
    known_measurements: set[str] | None = None,
    measurement_values: dict | None = None,
) -> list:
    """G1 -> G2 -> G5 -> G3, stopping at the first failure (brief §10).

    Order is COST order, not the order the brief lists them in: the free
    deterministic checks run before the paid one, so a draft with an
    invented number never reaches the verifier and never costs anything
    to reject. G4 is `astro build` in CI and is not runnable from here.

    There is no retry and no override. A draft that fails a gate is
    rejected and logged, full stop — a gate you can re-roll is not a
    gate.
    """
    registry = load_registry()
    results = []

    results.append(g1_numeric_grounding(draft["body"], source_text))
    if not results[-1]:
        return results

    if release:
        results.append(g2_entity_grounding(release, source_text, registry))
        if not results[-1]:
            return results
    if model_names:
        results.append(g2_models_resolve(model_names, registry))
        if not results[-1]:
            return results

    if benchmark_refs:
        results.append(
            g5_reference_integrity(
                draft["body"],
                benchmark_refs,
                known_measurements or set(),
                measurement_values or {},
            )
        )
        if not results[-1]:
            return results

    results.append(g3_verifier(llm, draft["body"], source_text))
    return results


def publish(
    ctx,
    candidate: "Candidate",
    *,
    channel: str,
    section_rules: str = "",
    release: dict | None = None,
    benchmark_refs: list[str] | None = None,
    instructions: str | None = None,
) -> str | None:
    """Fetch, draft, verify, write. Returns the slug, or None.

    In a dry run everything up to the write happens for real — the
    fetch, the draft, every gate — and then nothing is written. That is
    what makes "would this have published, and would the gates have let
    it?" an answerable question without publishing anything.
    """
    llm, dry_run = ctx.llm, ctx.dry_run
    item = candidate.item

    source_text = fetch_article_text(item.url, draft_module.ARTICLE_MAX_CHARS)
    if len(source_text) < 200:
        # No source text means G1 has nothing to check against, and a
        # numeric-grounding gate with an empty source would either pass
        # everything or fail everything. Neither is a gate.
        print(f"    Skipping — could not read enough source text from {item.url}",
              file=sys.stderr)
        reject(channel, "below_quality_gate", title=item.title, url=item.url,
               detail="source text unavailable; G1 cannot be evaluated",
               dry_run=dry_run)
        return None

    task = draft_module.build_article_task(
        item.title, item.source.name, source_text, instructions
    )
    drafted = draft_module.call_model(
        llm,
        task,
        section=candidate.section,
        fmt=candidate.format,
        section_rules=section_rules,
        fallback_topics=candidate.topics,
    )
    if drafted is None:
        if llm.offline:
            # There is deliberately NO deterministic stand-in for prose.
            # Everything upstream — classification, both scoring stages,
            # dedup, the budget — has one, because those are DECISIONS
            # and a decision can be replayed. Writing a post is not, and
            # a template pretending to be one would make an offline dry
            # run look like it had proved something it had not.
            #
            # This branch reports what would have been drafted so the
            # budget arithmetic is still answerable. It sits AFTER the
            # draft attempt and not before it, deliberately: an earlier
            # version short-circuited at the top of this function and
            # thereby skipped the gates entirely, which meant an offline
            # run could report "would publish" for a draft the gates
            # would have rejected. There is now no path to a slug that
            # does not pass through run_gates below.
            print(f"    [offline] no draft (no model); would have verified "
                  f"{item.title[:60]!r} for {candidate.section} "
                  f"(q={candidate.quality.total if candidate.quality else '-'} "
                  f"r={candidate.relevance.total if candidate.relevance else '-'})")
            ctx.ledger.record(
                "would-publish:" + candidate.id, channel, candidate.section,
                quality=candidate.quality.total if candidate.quality else None,
                relevance=candidate.relevance.total if candidate.relevance else None,
            )
        return None

    results = run_gates(
        llm,
        drafted,
        source_text,
        release=release,
        benchmark_refs=benchmark_refs,
    )
    for result in results:
        status = "pass" if result.passed else "FAIL"
        print(f"    {result.gate} {status}: {result.detail}")
    failed = next((r for r in results if not r.passed), None)
    if failed is not None:
        reject(
            channel,
            GATE_REASONS.get(failed.gate, "below_quality_gate"),
            title=drafted["title"],
            url=item.url,
            score=candidate.quality.total if candidate.quality else None,
            detail={"gate": failed.gate, "why": failed.detail,
                    "offending": failed.offending},
            dry_run=dry_run,
        )
        return None

    scout_block = {
        "qualityScore": candidate.quality.total if candidate.quality else 0,
        "relevanceScore": candidate.relevance.total if candidate.relevance else 0,
        "whyRelevant": candidate.why,
        "candidateId": candidate.id,
    }
    text = render(
        drafted,
        kind=candidate.section,
        fmt=candidate.format,
        model=llm_module.BLOG_MODEL,
        source_url=item.url,
        source_name=item.source.name,
        release=release,
        benchmark_refs=benchmark_refs,
        scout=scout_block,
    )

    if dry_run:
        from .frontmatter import slugify

        slug = slugify(drafted["title"])
        print(f"    [dry-run] would write src/content/blog/{slug}.md "
              f"({len(drafted['body'].split())} words, "
              f"q={scout_block['qualityScore']} r={scout_block['relevanceScore']})")
    else:
        slug = write_post(text, drafted["title"])
        print(f"    -> src/content/blog/{slug}.md")

    ctx.radar.set_status(candidate.id, "promoted", promoted_to=slug)
    ctx.ledger.record(
        slug,
        channel,
        candidate.section,
        quality=scout_block["qualityScore"],
        relevance=scout_block["relevanceScore"],
    )
    return slug


def publish_ranked(
    ctx,
    outcome: Outcome,
    *,
    channel: str,
    section: str,
    section_rules: str = "",
) -> int:
    """Budget, then publish, then queue the rest.

    The loop STOPS at the first budget refusal rather than continuing:
    the candidates are already sorted by relevance, so once there is no
    room for the best one there is no room for a worse one, and asking
    the ledger again per candidate would fill rejected.jsonl with one
    identical line per item. Everything from the refusal onwards is
    queued — it was good enough, there was just no room — and stays
    eligible until queue_ttl_days expires it back to the Radar.
    """
    published = 0
    exhausted = False

    for candidate in outcome.ranked:
        row = {
            "url": candidate.item.url,
            "title": candidate.item.title,
            "section": candidate.section,
            "topics": candidate.topics,
            "candidateId": candidate.id,
            "qualityScore": candidate.quality.total if candidate.quality else 0,
            "relevanceScore": candidate.score,
            "whyRelevant": candidate.why,
        }
        if exhausted:
            ctx.queue.put(channel, row, candidate.score)
            continue

        verdict = ctx.ledger.can_publish(section, published)
        if not verdict:
            ctx.ledger.refuse(channel, verdict, title=candidate.item.title,
                              score=candidate.score)
            ctx.queue.put(channel, row, candidate.score)
            exhausted = True
            continue

        print(f"  Writing: {candidate.item.title[:70]} "
              f"(q={row['qualityScore']} r={row['relevanceScore']})")
        slug = publish(ctx, candidate, channel=channel, section_rules=section_rules)
        if slug:
            published += 1
            ctx.queue.drop(row)

    if exhausted:
        print(f"  Budget reached after {published} post(s); "
              f"{len([c for c in outcome.ranked]) - published} candidate(s) queued.")
    return published
