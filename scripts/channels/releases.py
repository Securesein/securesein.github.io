"""
The Model Updates channel — "What is new in the model landscape?"
(brief §8.1).

    python scripts/run.py --channel releases --dry-run

Ported from the superseded channels-releases-benchmarks branch, where
this logic was built and validated against real feed data. What changed
here is only what the new brief changed: the section is `release` rather
than a fourth `kind`, every post carries a `format` and a `scout` block,
the budget is keyed by section, and candidates that lose on budget land
on the Radar instead of only in the queue.

Ten steps, and the fifth one is the reason the channel exists:

  1. fetch every source in feeds-releases.json
  2. drop anything already seen
  3. classify into an eventType plus the structured facts
  4. resolve vendor and family through models.json; unresolved -> drop
  5. ENTITY DEDUP on (vendor, family, version, eventType)
  6. score against the rubric in config/releases.json
  7. below threshold -> reject with a reason; at or above -> enqueue
  8. publish the top of the queue, up to the budget
  9. draft -> gates G1-G3 -> frontmatter -> commit
 10. trigger deploy.yml explicitly (the workflow does this)

Step 5 is what URL-level dedup cannot do. The News archive already
holds three separate posts about one GPT-6 Astra release, from three
different URLs with three different headlines — the exact failure this
channel is built to make impossible. scripts/tests/test_releases.py
replays those three items through this pipeline and asserts they
collapse into one candidate.

Two rules are enforced in code rather than in a prompt, because a
prompt follows a rule most of the time and "most of the time" is the
wrong number for something that publishes unreviewed:

  - only a `tier: primary` source can trigger a post. Press and
    aggregator sources can corroborate an existing candidate and add a
    point to its score, and that is all they can ever do.
  - an unresolved vendor or family is dropped and logged. It never
    becomes a new registry entry.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from core import classify as classify_module
from core import llm as llm_module
from core.constants import CONFIG_DIR, FEEDS_RELEASES_FILE, SEEN_RELEASES_FILE
from core.dedup import EntityIndex, EntityKey
from core.feeds import (
    TIER_PRIMARY,
    Item,
    fetch,
    fetch_article_text,
    load_fixture,
    load_sources,
)
from core import pipeline
from core import taxonomy as tax
from core.profile import (
    TopicActivity,
    profile as load_profile_object,
    quality_gate,
    quality_gate_offline,
    relevance_rank,
    why_relevant,
)
from core.radar import radar_id
from core.registry import load_registry
from core.state import park_unresolved_model, read_json, reject, write_json

CHANNEL = "releases"
# The section this channel publishes into. Budgets are keyed by SECTION,
# not by channel — see core/ledger.py.
SECTION = "release"
CONFIG_FILE = CONFIG_DIR / "releases.json"

# How recently a corroborating source has to have said the same thing
# for it to count as corroboration rather than as an echo.
CORROBORATION_WINDOW_HOURS = 48


def load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


@dataclass
class Candidate:
    item: Item
    facts: dict
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    corroborators: list[str] = field(default_factory=list)
    material_facts: list[str] = field(default_factory=list)

    @property
    def key(self) -> EntityKey:
        return EntityKey(
            vendor=self.facts.get("vendor", ""),
            family=self.facts.get("family", ""),
            version=self.facts.get("version", ""),
            event_type=self.facts.get("eventType", ""),
        )

    def as_row(self) -> dict:
        return {
            "title": self.item.title,
            "url": self.item.url,
            "source": self.item.source.name,
            "tier": self.item.source.tier,
            "entity": str(self.key),
            "eventType": self.facts.get("eventType"),
            "vendor": self.facts.get("vendor"),
            "family": self.facts.get("family"),
            "version": self.facts.get("version"),
            "openWeights": self.facts.get("openWeights"),
            "modality": self.facts.get("modality"),
            "classifier": self.facts.get("classifier"),
            "score": round(self.score, 2),
            "scoreReasons": self.reasons,
            "corroborators": self.corroborators,
            "materialFacts": self.material_facts,
        }


# --- step 6: the rubric ---------------------------------------------


def score_candidate(candidate: Candidate, config: dict, in_cooldown: bool) -> Candidate:
    """Every point is attributed, so a score is readable rather than
    just a number — which is what makes the threshold tunable from
    state/queue.json after a dry-run week."""
    weights = config["weights"]
    tier1 = set(config.get("tier1_vendors", []))
    facts = candidate.facts
    total = 0.0
    reasons: list[str] = []

    def add(name: str, condition: bool = True) -> None:
        nonlocal total
        if not condition or name not in weights:
            return
        total += weights[name]
        reasons.append(f"{name} {weights[name]:+g}")

    add("primary_source", candidate.item.source.tier == TIER_PRIMARY)

    event = facts.get("eventType", "")
    if event == "new_model":
        add("event_new_model")
    elif event == "version_bump":
        if classify_module.is_major(facts.get("version", "")):
            add("event_version_bump_major")
        else:
            add("event_version_bump_minor")
    elif event == "capability_update":
        add("event_capability_update")
    elif event == "deprecation":
        add("event_deprecation")
    elif event == "availability":
        add("event_availability")

    add("open_weights", bool(facts.get("openWeights")))

    vendor = facts.get("vendor", "")
    if vendor in tier1:
        add("tier1_vendor")
    else:
        # Brief §14.4, default applied and flagged in config/releases.json:
        # every vendor is tracked, but a non-tier-1 vendor carries an
        # explicit extra hurdle rather than a separate threshold.
        add("non_tier1")

    text = f"{candidate.item.title}\n{candidate.item.summary}"
    add("benchmark_claims_present", classify_module.has_benchmark_claim(text))
    add("corroborated_48h", bool(candidate.corroborators))
    add("press_release_only", bool(classify_module.PRESS_RELEASE.search(text)))
    add("entity_in_cooldown", in_cooldown)

    candidate.score = total
    candidate.reasons = reasons
    return candidate


# --- the run ---------------------------------------------------------


def _seen() -> tuple[set[str], bool]:
    """(already-seen ids, is_first_run).

    The first run has no baseline, so *everything* currently visible is
    "new" — and several sources here are back catalogues rather than
    feeds. A Hugging Face org endpoint hands back thirty repositories
    whether they were published this morning or in 2023, so a first run
    without a baseline would enqueue an entire lab's history as
    brand-new releases. The News channel already learned this the hard
    way (see `is_first_run` in fetch_and_notify.py); this is the same
    protection."""
    if not SEEN_RELEASES_FILE.exists():
        return set(), True, set()
    state = read_json(SEEN_RELEASES_FILE, {"ids": [], "sources": []})
    return set(state["ids"]), False, set(state.get("sources", []))


def _remember(ids: set[str], dry_run: bool, sources: set[str] | None = None) -> None:
    """Written in a dry run too, deliberately.

    This file is a *cursor*, not a publication record — the same
    category as state/queue.json, which a dry run also writes. Holding
    it back would make every dry run a first run, re-scanning the same
    several hundred items forever and never showing what a *second*
    run looks like, which is the whole thing the Phase 3 dry-run week
    is supposed to measure. Nothing here can cause a publication:
    ledger.json and entities.json, which can, stay untouched.
    """
    # Bounded: the oldest ids can never come back as new, because the
    # recency window would drop them anyway.
    write_json(SEEN_RELEASES_FILE, {
        "ids": sorted(ids)[-20000:],
        "sources": sorted(sources or []),
    })
    if dry_run:
        print(f"    [dry-run] {len(ids)} item id(s) recorded as seen "
              f"(a cursor, not a publication).")


def _passes_volume_filter(item: Item, config: dict) -> bool:
    """Two feeds carry an entire cloud's worth of announcements, of
    which a fraction of a percent are model releases (brief §12.1d).
    Filtering them here, before classification, is the difference
    between a candidate pool and a firehose."""
    needles = config.get("volume_filtered_sources", {}).get(item.source.name)
    if not needles:
        return True
    haystack = f"{item.title} {item.summary}".lower()
    return any(needle in haystack for needle in needles)


def _material_facts(item: Item, facts: dict) -> list[str]:
    """What would make a second sighting of an already-covered entity
    worth an update rather than a drop."""
    text = f"{item.title}\n{item.summary}".lower()
    found = []
    if facts.get("eventType") == "availability" or "generally available" in text:
        found.append("ga_date")
    if any(word in text for word in ("price", "pricing", "per million", "$")):
        found.append("pricing")
    if facts.get("openWeights"):
        found.append("open_weights")
    if classify_module.has_benchmark_claim(text):
        found.append("benchmark_claim")
    if facts.get("eventType") == "deprecation":
        found.append("deprecation")
    return found


def _recent_enough(item: Item) -> bool:
    if not item.published:
        return True  # a source with no timestamps is not evidence of age
    try:
        when = datetime.fromisoformat(item.published)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when >= datetime.now(timezone.utc) - timedelta(hours=CORROBORATION_WINDOW_HOURS)


def gather(ctx, config: dict, sources=None) -> list[Item]:
    """Steps 1-2. Returns unseen items across every in-scope source, or
    out of a recorded fixture when one is given."""
    if ctx.fixtures is not None:
        path = ctx.fixtures
        if path.is_dir():
            items: list[Item] = []
            for fixture in sorted(path.glob("*.json")):
                items.extend(load_fixture(fixture))
            return items
        return load_fixture(path)

    sources = sources if sources is not None else load_sources(FEEDS_RELEASES_FILE)
    seen, first_run, known_sources = _seen()
    max_age = int(config.get("max_item_age_days", 14))

    items: list[Item] = []
    everything: set[str] = set(seen)
    sources_now: set[str] = set(known_sources)
    for source in sources:
        # A source running for the FIRST time gets the same baseline
        # the channel itself gets on its first run: everything it shows
        # is recorded as seen and nothing is published from it.
        #
        # Without this, adding a feed is a spike. Every item on it is
        # unseen, so dedup removes none of them, and the age filter
        # cannot help where a page carries no dates — _older_than
        # treats a missing timestamp as "not evidence of age" and lets
        # it through, which is right for a real feed and exactly wrong
        # for an entire back catalogue arriving at once. x.ai/news
        # lists thirty undated posts.
        new_source = source.name not in known_sources
        sources_now.add(source.name)

        for item in fetch(source, limit=ctx.limit or 30):
            everything.add(item.id)
            if new_source or item.id in seen:
                continue
            if not _passes_volume_filter(item, config):
                continue
            # A release is news for about a fortnight. The age filter is
            # what stops a back-catalogue endpoint (every Hugging Face
            # org feed is one) from presenting 2023 as this morning.
            if _older_than(item, max_age):
                continue
            items.append(item)

    if first_run:
        print(f"  First run: recording a baseline of {len(everything)} item(s) "
              f"and publishing nothing. Future runs only see what is new.")
        _remember(everything, ctx.dry_run, sources_now)
        return []

    baselined = sources_now - known_sources
    if baselined:
        print(f"  {len(baselined)} new source(s) baselined, publishing nothing from "
              f"them this run: {', '.join(sorted(baselined))}")

    _remember(everything, ctx.dry_run, sources_now)
    return items


def _older_than(item: Item, days: int) -> bool:
    if not item.published:
        return False  # a source with no timestamps is not evidence of age
    try:
        when = datetime.fromisoformat(item.published)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when < datetime.now(timezone.utc) - timedelta(days=days)


def build_candidates(ctx, items: list[Item], config: dict) -> tuple[list[Candidate], list[Item]]:
    """Steps 3-5. Returns (candidates, corroborating items)."""
    registry = load_registry()
    candidates: list[Candidate] = []
    corroborating: list[Item] = []

    for item in items:
        facts = classify_module.classify(
            ctx.llm, item, registry, llm_module.CLASSIFY_MODEL
        )
        event = facts.get("eventType", classify_module.NONE)
        if event == classify_module.NONE:
            reject(CHANNEL, "not_a_release", title=item.title, url=item.url,
                   detail=facts.get("classifier"), dry_run=ctx.dry_run)
            continue

        # A non-primary source can corroborate, never trigger. Enforced
        # here, in code, and not asked of a prompt.
        if not item.source.may_trigger:
            corroborating.append(item)
            continue

        if not facts.get("vendor") or not facts.get("family"):
            hint = facts.get("modelHint") or item.title
            park_unresolved_model(hint, f"releases/{item.source.name}", url=item.url)
            reject(CHANNEL, "unresolved_vendor", title=item.title, url=item.url,
                   detail=facts, dry_run=ctx.dry_run)
            continue

        candidate = Candidate(item=item, facts=facts)
        candidate.material_facts = _material_facts(item, facts)
        candidates.append(candidate)

    return candidates, corroborating


def collapse(candidates: list[Candidate]) -> list[Candidate]:
    """Step 5, the in-run half: several sources announcing one release
    inside a single run are ONE candidate, not several.

    The survivor is the one from the strongest source, and every other
    sighting becomes a corroborator on it — which is also how a
    candidate earns its `corroborated_48h` point. This is the mechanism
    that turns three GPT-6 Astra items into one post.
    """
    by_entity: dict[str, Candidate] = {}
    for candidate in candidates:
        key = str(candidate.key)
        winner = by_entity.get(key)
        if winner is None:
            by_entity[key] = candidate
            continue
        loser, winner = _rank(winner, candidate)
        winner.corroborators.append(f"{loser.item.source.name}: {loser.item.title}")
        winner.material_facts = sorted(set(winner.material_facts) | set(loser.material_facts))
        by_entity[key] = winner
    return list(by_entity.values())


def _rank(a: Candidate, b: Candidate) -> tuple[Candidate, Candidate]:
    """(loser, winner). A primary source outranks anything else; after
    that, the earlier timestamp wins, because the first announcement is
    the release and the rest are coverage of it."""
    a_primary = a.item.source.tier == TIER_PRIMARY
    b_primary = b.item.source.tier == TIER_PRIMARY
    if a_primary != b_primary:
        return (b, a) if a_primary else (a, b)
    if (a.item.published or "9") <= (b.item.published or "9"):
        return b, a
    return a, b


def attach_corroboration(candidates: list[Candidate], corroborating: list[Item]) -> None:
    """A press or aggregator item mentioning the same family within the
    corroboration window adds a point — and only a point."""
    for item in corroborating:
        if not _recent_enough(item):
            continue
        haystack = f"{item.title} {item.summary}".lower()
        for candidate in candidates:
            # Match on the family's parts rather than the slug: the
            # family id is "gpt-astra" and the prose says "GPT-6 Astra",
            # so a substring test on the slug never fires.
            parts = [p for p in (candidate.facts.get("family") or "").split("-") if len(p) > 2]
            if parts and all(part in haystack for part in parts):
                candidate.corroborators.append(f"{item.source.name}: {item.title}")


def run(ctx) -> int:
    config = load_config()
    ledger, queue = ctx.ledger, ctx.queue
    entities = EntityIndex(
        cooldown_days=int(config.get("cooldown_days", 10)), dry_run=ctx.dry_run
    )

    expired = queue.prune()
    for item in expired:
        # §9: a candidate that waits longer than queue_ttl_days is stale
        # news and falls back to the Radar rather than being published
        # late. Logged with a BUDGET reason, not a quality one — nothing
        # was wrong with it except the week it arrived in.
        reject(CHANNEL, "queue_expired", title=item.get("title", ""),
               url=item.get("url", ""), score=item.get("score"),
               detail="expired from the queue before budget freed up",
               dry_run=ctx.dry_run)

    items = gather(ctx, config)
    print(f"{len(items)} unseen item(s) across the release sources.")

    candidates, corroborating = build_candidates(ctx, items, config)
    print(f"  {len(candidates)} classified as a release, "
          f"{len(corroborating)} corroborating-only.")

    before = len(candidates)
    candidates = collapse(candidates)
    if before != len(candidates):
        print(f"  entity dedup collapsed {before} sightings into "
              f"{len(candidates)} distinct release(s).")
    attach_corroboration(candidates, corroborating)

    scored: list[Candidate] = []
    updates: list[tuple[Candidate, object]] = []
    for candidate in candidates:
        action, coverage = entities.decide(candidate.key, candidate.material_facts)
        if action == "drop":
            reject(CHANNEL, "entity_covered", title=candidate.item.title,
                   url=candidate.item.url,
                   detail=f"{candidate.key} already covered by {coverage.slug}",
                   dry_run=ctx.dry_run)
            continue
        if action == "update":
            updates.append((candidate, coverage))
            continue
        scored.append(score_candidate(candidate, config, in_cooldown=False))

    threshold = float(config["threshold"])
    prof = load_profile_object()
    from core.frontmatter import existing_posts

    activity = TopicActivity.from_archive(prof, existing_posts())

    for candidate in scored:
        if candidate.score < threshold:
            reject(CHANNEL, "below_threshold", title=candidate.item.title,
                   url=candidate.item.url, score=candidate.score,
                   detail=candidate.reasons, dry_run=ctx.dry_run)
            continue

        # The release rubric above is the SECTION gate (§8.1): is this a
        # model release worth a post at all. The §7.1 two-stage scoring
        # runs on top of it and produces the numbers that are recorded —
        # so a `scout.qualityScore` means the same thing on a Model
        # Updates post as on a Research one, which is the only way the
        # digest's scores are comparable across sections.
        topics = tax.valid_topics(_topics_for(candidate))
        quality = (quality_gate_offline(candidate.item, prof) if ctx.llm.offline
                   else quality_gate(ctx.llm, candidate.item, prof))
        relevance = relevance_rank(
            candidate.item, SECTION, topics, prof,
            starvation_bonus=activity.bonus(topics),
        )
        why = why_relevant(ctx.llm, candidate.item, SECTION, topics, relevance, prof)

        ctx.radar.add(
            url=candidate.item.url, title=candidate.item.title,
            source=candidate.item.source.name, section=SECTION, topics=topics,
            quality=quality.total, relevance=relevance.total, why=why,
        )

        row = candidate.as_row()
        row.update(
            qualityScore=quality.total,
            relevanceScore=relevance.total,
            whyRelevant=why,
            candidateId=radar_id(candidate.item.url, candidate.item.title),
            topics=topics,
        )
        queue.put(CHANNEL, row, candidate.score)

    for candidate, coverage in updates:
        # Consumes no budget and mints no new URL, by design.
        print(f"  UPDATE {coverage.slug}: {candidate.key} gained "
              f"{', '.join(candidate.material_facts)}")

    ready = queue.top(CHANNEL, limit=100)
    print(f"  {len(ready)} candidate(s) at or above the threshold of {threshold}.")
    for row in ready[:10]:
        print(f"    {row['score']:>5.1f}  {row['entity']:<45} {row['title'][:60]}")

    published = 0
    for row in ready:
        verdict = ledger.can_publish(SECTION, published)
        if not verdict:
            ledger.refuse(CHANNEL, verdict, title=row["title"], score=row["score"])
            # Everything still in the queue when the budget runs out is
            # also put on the Radar, so the digest can show what was
            # held back rather than only what was published.
            break
        if publish_one(ctx, row, entities):
            queue.drop(row)
            published += 1

    entities.save()
    return published


# --- steps 9-10: draft, verify, emit ---------------------------------


DRAFT_PROMPT = """Write a short release note for a blog about applied
AI, read by developers, IT/sysadmins and enterprise architects.

Short. No introduction, no conclusion, no "in this article we will".
Target 150-300 words. Five things, in this order, as flowing prose with
no headings:

1. One sentence: what shipped, from whom.
2. What changed versus the previous version — context window, modality,
   pricing, reasoning settings, licence. Be concrete.
3. Where you can actually run it: API, cloud provider, open weights,
   local runtimes.
4. What the vendor claims, EXPLICITLY attributed as a vendor claim
   ("OpenAI says...", "according to the model card..."). Never state a
   vendor's performance number as established fact.
5. Nothing else. The source link is added automatically.

HARD RULES:
- Every number you write must appear verbatim in the source text below.
  Do not round, do not convert, do not recall a figure from elsewhere.
  A number that is not in the source will be caught and the post
  discarded.
- If you cannot fill points 2 AND 3 from the source, this was not a
  release. Return {{"insufficient": true}} and nothing else.

SOURCE ({publisher}):
{source}

TOPICS — CLOSED LIST. Pick 1-3 exact slugs, nothing else:
{topics}

Return ONLY JSON:
{{"title": "...", "description": "one sentence lede",
  "topics": ["..."], "body": "markdown, no h1, no headings"}}"""


def _draft(ctx, row: dict, source_text: str, topics: dict) -> dict | None:
    topic_list = "\n".join(
        f'- "{slug}": {info["label"]} — {info["description"]}'
        for slug, info in topics.items()
    )
    data = ctx.llm.json(
        DRAFT_PROMPT.format(
            publisher=row.get("source", ""),
            source=source_text[:8000],
            topics=topic_list,
        ),
        model=llm_module.BLOG_MODEL,
        temperature=0.4,
        label="release draft",
    )
    if not isinstance(data, dict):
        return None
    if data.get("insufficient"):
        reject(CHANNEL, "no_product_angle", title=row["title"], url=row["url"],
               detail="the model could not fill what-changed and where-to-run "
                      "from the source",
               dry_run=ctx.dry_run)
        return None
    if not data.get("title") or not data.get("body"):
        return None

    valid = [t for t in (data.get("topics") or []) if t in topics][:3]
    if not valid:
        reject(CHANNEL, "no_valid_topic", title=row["title"], url=row["url"],
               dry_run=ctx.dry_run)
        return None
    return {
        "title": str(data["title"]).strip(),
        "description": str(data.get("description", "")).strip() or row["title"],
        "topics": valid,
        "body": str(data["body"]).strip(),
    }


def publish_one(ctx, row: dict, entities: EntityIndex) -> bool:
    """Draft, run the gates, emit. Returns whether it would publish.

    Nothing here bypasses a gate in a dry run: the gates run for real,
    against the real source text, and only the final write is
    suppressed. A dry run that reports "would publish" has therefore
    actually passed G1, G2 and G3.
    """
    from core.frontmatter import render, write_post
    from core.measurements import Store
    from core.verify import run_release_gates

    registry = load_registry()
    topics = _topics()

    source_text = fetch_article_text(row["url"], 8000)
    if len(source_text) < 200:
        reject(CHANNEL, "not_a_release", title=row["title"], url=row["url"],
               detail="could not fetch enough source text to ground a draft",
               dry_run=ctx.dry_run)
        return False

    draft = _draft(ctx, row, source_text, topics)
    if draft is None:
        return False

    release = {
        "vendor": row["vendor"],
        "family": row["family"],
        "version": row.get("version") or None,
        "eventType": row["eventType"],
        "openWeights": bool(row.get("openWeights")),
        "modality": row.get("modality") or ["text"],
        "modelHint": row.get("modelHint", ""),
    }

    for result in run_release_gates(ctx.llm, draft, release, source_text, registry):
        print(f"    {result.gate}: {'pass' if result.passed else 'FAIL'} — {result.detail}")
        if result.passed:
            continue
        reject(CHANNEL, GATE_REASONS[result.gate], title=draft["title"],
               url=row["url"], score=row.get("score"),
               detail={"gate": result.gate, "why": result.detail,
                       "offending": result.offending, "draft": draft["body"][:2000]},
               dry_run=ctx.dry_run)
        return False

    # §6.4: any benchmark number in a release post is also written to
    # the measurements collection as a vendor claim. The two channels
    # share one factual substrate; a number that exists only in prose is
    # not allowed.
    claims = _benchmark_claims(draft, release, row, registry)
    store = Store(dry_run=ctx.dry_run)
    if claims:
        store.upsert(claims)
        refs = list(getattr(store, "pending", {}).keys())
        store.save()
        print(f"    cross-wrote {len(claims)} vendor benchmark claim(s)")
    else:
        refs = []

    scout = {
        "qualityScore": row.get("qualityScore", 0),
        "relevanceScore": row.get("relevanceScore", 0),
        "whyRelevant": row.get("whyRelevant")
                       or f"Primary-source {release['eventType'].replace('_', ' ')} "
                          f"for {release['family']}.",
        "candidateId": row.get("candidateId") or radar_id(row["url"], row["title"]),
    }
    text = render(
        draft,
        kind=SECTION,
        # A release note is a short timely item written from the source
        # — the `news` shape, in a different section. Under the
        # three-axis model that is exactly what format is for.
        fmt="news",
        model=llm_module.BLOG_MODEL,
        source_url=row["url"],
        source_name=row.get("source", "Unknown"),
        release={k: v for k, v in release.items() if k != "modelHint"},
        benchmark_refs=refs,
        scout=scout,
    )

    if ctx.dry_run:
        print(f"  [dry-run] would publish {draft['title']!r} "
              f"({len(draft['body'].split())} words, {len(refs)} benchmarkRef(s))")
        slug = "would-publish"
    else:
        slug = write_post(text, draft["title"])
        print(f"    -> src/content/blog/{slug}.md")

    ctx.radar.set_status(scout["candidateId"], "promoted", promoted_to=slug)
    ctx.ledger.record(slug, CHANNEL, SECTION,
                      quality=scout["qualityScore"], relevance=scout["relevanceScore"])
    entities.record(
        EntityKey(release["vendor"], release["family"], release["version"] or "",
                  release["eventType"]),
        slug,
        row.get("materialFacts", []),
    )
    return True


GATE_REASONS = {
    "G1": "gate_g1_ungrounded_number",
    "G2": "gate_g2_entity_not_in_source",
    "G3": "gate_g3_verifier_rejected",
    "G5": "gate_g5_dangling_reference",
}


def _topics() -> dict:
    return tax.topics()


def _topics_for(candidate: Candidate) -> list[str]:
    """Provisional topics for a release candidate, from the same
    deterministic patterns the axes classifier uses. The drafter picks
    the final set; these exist so the starvation bonus and the Radar
    record have something real to work with before the draft exists."""
    from core.classify import TOPIC_PATTERNS

    text = f"{candidate.item.title}\n{candidate.item.summary}"
    found = [s for s, p in TOPIC_PATTERNS.items() if p.search(text)]
    found.sort(key=lambda s: -len(TOPIC_PATTERNS[s].findall(text)))
    return found or ["llms"]


def _benchmark_claims(draft: dict, release: dict, row: dict, registry) -> list[dict]:
    """Benchmark figures stated in a release post, as vendor claims.

    Only tracked benchmarks, only figures that are actually next to the
    benchmark's name, and only when the model resolves. Everything else
    is left in the prose — where G1 has already proved it came from the
    source."""
    from backfill_vendor_benchmarks import SPELLINGS, _vendor_label, sentences
    from core.verify import NUMBER

    model = registry.resolve_model(release.get("modelHint") or release["family"])
    if model is None:
        return []

    claims = []
    for sentence in sentences(draft["body"]):
        for slug, pattern in SPELLINGS.items():
            if not re.search(pattern, sentence, re.I):
                continue
            figures = [m for m in NUMBER.finditer(sentence) if m.group(4)]
            if len(figures) != 1:
                continue  # ambiguous pairing is not a claim we can record
            benchmark = registry.resolve_benchmark(slug)
            claims.append({
                "model": model.id,
                "vendor": model.vendor,
                "benchmark": benchmark.slug,
                "metric": benchmark.metric,
                "value": float(figures[0].group(1).replace(",", "")
                               + ("." + figures[0].group(2) if figures[0].group(2) else "")),
                "unit": benchmark.unit,
                "measuredBy": "vendor",
                "evaluator": _vendor_label(model.vendor, row.get("source", "")),
                "conditions": {
                    "notes": "Vendor claim from the release announcement; run "
                             "conditions not published with the figure."
                },
                "measuredAt": (row.get("published") or "")[:10] or _today(),
                "sourceUrl": row["url"],
                "publisher": row.get("source", "Unknown"),
            })
    return claims


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
