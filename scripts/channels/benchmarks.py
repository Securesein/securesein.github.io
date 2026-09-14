"""
The Benchmarks channel (brief §7).

    python scripts/run.py --channel benchmarks --dry-run

    1. run each adapter; normalise to the collection schema
    2. resolve model + benchmark through the registries; park what
       cannot be resolved
    3. upsert measurements (no-op / supersede / new)
    4. commit the collection changes — THIS ALONE IS A COMPLETE RUN.
       Most days produce data and no post.
    5. evaluate post triggers against the new state
    6. if the trigger score clears the threshold and there is budget,
       draft one roundup covering everything that has fired since the
       last one

Measurement commits do not consume post budget. Only roundups do.

**Adapters are independent and wrapped.** One broken scraper must never
stop the Epoch pull landing, so every adapter runs inside its own
try/except and a failure becomes a line in state/adapter_failures.jsonl
and an entry in the weekly report — never an exit code.

Exactly one adapter is built: Epoch AI. That is deliberate and it is
what §7.1 asks for — Epoch first and completely, everything else
provisional until Phase 4 shows what its coverage is missing. Of the
twelve tracked benchmarks, Epoch covers nine; MMLU-Pro, LMArena Text
Elo and LiveCodeBench have no adapter and therefore no rows, which is
the correct empty rather than a silently wrong number.
"""

from __future__ import annotations

import sys
import traceback

from channels import benchmark_triggers
from core import llm as llm_module
from core.adapters import epoch
from core.constants import EPOCH_BACKFILL_START
from core.measurements import Store
from core.registry import load_registry
from core.state import log_adapter_failure, park_unresolved_model, reject

CHANNEL = "benchmarks"
# Budgets are keyed by SECTION, not by channel (core/ledger.py).
SECTION = "benchmark"

# name -> callable(registry, ctx) -> (measurements, unresolved)
ADAPTERS = {
    "epoch": lambda registry, ctx: epoch.collect(
        registry,
        bundle_path=ctx.fixtures if ctx.fixtures and ctx.fixtures.suffix == ".zip" else None,
        since=EPOCH_BACKFILL_START,
    ),
}


def collect(ctx) -> tuple[list[dict], list[dict], list[str]]:
    """Steps 1-2. Returns (measurements, unresolved, failed adapters)."""
    registry = load_registry()
    measurements: list[dict] = []
    unresolved: list[dict] = []
    failed: list[str] = []

    for name, adapter in ADAPTERS.items():
        try:
            rows, parked = adapter(registry, ctx)
        except Exception as exc:  # noqa: BLE001 — a dead adapter is data, not a crash
            failed.append(name)
            log_adapter_failure(name, f"{type(exc).__name__}: {exc}")
            print(f"  adapter {name} FAILED: {exc}", file=sys.stderr)
            if ctx.dry_run:
                traceback.print_exc()
            continue
        print(f"  adapter {name}: {len(rows)} measurement(s), "
              f"{len(parked)} unresolved model name(s)")
        measurements.extend(rows)
        unresolved.extend(parked)

    return measurements, unresolved, failed


def run(ctx) -> int:
    print(f"Ingesting benchmark measurements from {EPOCH_BACKFILL_START} onward.")
    measurements, unresolved, failed = collect(ctx)

    # §4.1: parked, never auto-registered, and reported weekly. A human
    # decides whether an unresolved name is a new model or noise.
    for row in unresolved:
        park_unresolved_model(row["name"], row["source"], **{
            k: v for k, v in row.items() if k not in ("name", "source")
        })
    if unresolved:
        print(f"  {len(unresolved)} model name(s) parked in "
              f"state/unresolved_models.jsonl — none auto-registered.")

    store = Store(dry_run=ctx.dry_run)
    summary = store.upsert(measurements)
    print(f"  upsert: {summary['new']} new, {summary['superseded']} superseded, "
          f"{summary['unchanged']} unchanged, {summary['total_after']} total.")
    store.save()

    # Steps 5-6. Measurement commits consume no post budget; only a
    # roundup does, and only when the data has actually done something.
    fired = benchmark_triggers.evaluate(ctx, store)
    published = 0
    if fired:
        weight = benchmark_triggers.total_weight(fired)
        print(f"  {len(fired)} trigger(s) fired, total weight {weight}:")
        for trigger in fired:
            print(f"    +{trigger['weight']} {trigger['trigger']}: {trigger['detail']}")
        if benchmark_triggers.should_write_roundup(fired):
            published = _maybe_roundup(ctx, store, fired)
        else:
            print(f"  below the roundup threshold — data committed, no post.")
    else:
        print("  no triggers fired — data committed, no post. This is the normal case.")

    if failed:
        print(f"  {len(failed)} adapter(s) failed: {', '.join(failed)} "
              f"(logged, not fatal)")
    return published


ROUNDUP_PROMPT = """Write a short benchmark roundup for a blog about
applied AI, read by developers, IT/sysadmins and enterprise architects.

You are given a list of FINDINGS, each already verified against the
measurements collection. Write 200-400 words covering them, in
descending order of interest.

HARD RULES — a draft breaking any of these is discarded:
- Every number you write must be one of the numbers in the findings
  below, exactly as given. Do not round, do not average, do not add a
  figure from memory.
- Name who measured each number. A vendor's own claim must be called a
  vendor claim.
- Where a vendor's claim and an independent measurement disagree, say
  so plainly. Do not soften it and do not explain it away.
- No introduction, no conclusion, no "in this roundup we will".

FINDINGS:
{findings}

TOPICS — CLOSED LIST. Pick 1-3 exact slugs:
{topics}

Return ONLY JSON:
{{"title": "...", "description": "one sentence lede",
  "topics": ["..."], "body": "markdown, no h1"}}"""


def _maybe_roundup(ctx, store, fired: list[dict]) -> int:
    """Draft one roundup covering everything fired since the last one,
    put it through G5, and emit it. Budget is checked first, because the
    drafting call is the expensive part."""
    from core.frontmatter import render, write_post
    from core.verify import g5_reference_integrity
    from core import taxonomy as tax

    verdict = ctx.ledger.can_publish(SECTION, 0)
    if not verdict:
        ctx.ledger.refuse(CHANNEL, verdict, title="benchmark roundup", score=None)
        return 0

    refs: list[str] = []
    for trigger in fired:
        for ref in trigger["refs"]:
            if ref not in refs:
                refs.append(ref)

    known = {**store.existing, **getattr(store, "pending", {})}
    values = {ref: known[ref]["value"] for ref in refs if ref in known}

    findings = "\n".join(
        f"- [{t['trigger']}] {t['detail']}" for t in fired
    )
    topics = tax.topics()
    draft = ctx.llm.json(
        ROUNDUP_PROMPT.format(
            findings=findings,
            topics="\n".join(
                f'- "{slug}": {info["label"]} — {info["description"]}'
                for slug, info in topics.items()
            ),
        ),
        model=llm_module.BLOG_MODEL,
        temperature=0.4,
        label="benchmark roundup",
    )
    if not isinstance(draft, dict) or not draft.get("body"):
        print("  roundup drafting produced nothing usable — no post.")
        return 0

    valid = [t for t in (draft.get("topics") or []) if t in topics][:3]
    if not valid:
        reject(CHANNEL, "no_valid_topic", title=str(draft.get("title", "")),
               dry_run=ctx.dry_run)
        return 0
    draft = {
        "title": str(draft["title"]).strip(),
        "description": str(draft.get("description", "")).strip() or "Benchmark roundup.",
        "topics": valid,
        "body": str(draft["body"]).strip(),
    }

    # G5: every cited id exists, and every number in the prose traces to
    # one of the cited measurements. A roundup cites only numbers that
    # are in the collection — there is no path by which a figure reaches
    # a reader without also being a record someone can check.
    result = g5_reference_integrity(draft["body"], refs, set(known), values)
    print(f"    G5: {'pass' if result.passed else 'FAIL'} — {result.detail}")
    if not result:
        reject(CHANNEL, "gate_g5_dangling_reference", title=draft["title"],
               detail={"why": result.detail, "offending": result.offending,
                       "draft": draft["body"][:2000]},
               dry_run=ctx.dry_run)
        return 0

    # A roundup is a reading of measured numbers with the conditions
    # stated — the `benchmark` shape, which schema refinement 6 allows
    # only in this section.
    scout = {
        "qualityScore": 100.0,
        "relevanceScore": 100.0,
        "whyRelevant": "Triggered by: "
                       + "; ".join(t["trigger"] for t in fired)[:180],
        "candidateId": "benchmarks:" + refs[0] if refs else "benchmarks:roundup",
    }
    text = render(
        draft,
        kind=SECTION,
        fmt="benchmark",
        model=llm_module.BLOG_MODEL,
        benchmark_refs=refs,
        scout=scout,
    )
    if ctx.dry_run:
        print(f"  [dry-run] would publish roundup {draft['title']!r} "
              f"citing {len(refs)} measurement(s)")
        slug = "would-publish-roundup"
    else:
        slug = write_post(text, draft["title"])
        print(f"    -> src/content/blog/{slug}.md")
    ctx.ledger.record(slug, CHANNEL, SECTION,
                      quality=scout["qualityScore"],
                      relevance=scout["relevanceScore"])
    return 1
