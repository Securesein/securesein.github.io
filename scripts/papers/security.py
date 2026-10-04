#!/usr/bin/env python3
"""
Reader's second corpus: practitioner security intel.

    python scripts/papers/security.py            [--dry-run] (default)
    python scripts/papers/security.py --publish   (actually sends)
    python scripts/papers/security.py --offline-llm

**This never writes anything to the site.** It fetches, filters,
triages and sends one plain Telegram message. There is no write path to
src/content, the ledger, the budget files or any profile — the same
isolation Reader Phase 1 has, for the same reason. The owner reads the
digest and decides by hand whether anything in it deserves a post.

WHY A SECOND READER RATHER THAN A BUCKET IN THE FIRST. The papers
Reader draws one corpus — arXiv — through one funnel keyed on an
arXiv id, and the cs.CR bucket in config/papers_profile.yaml already
covers the security PAPERS. What it cannot reach is everything that is
not a paper: a writeup of a working prompt-injection chain, a scanner
release that adds a probe class, a threat-matrix revision, a CVE
against a model-serving package. Those arrive as ordinary RSS and Atom
from a dozen unrelated places, which is exactly what core/feeds.py
already ingests for the publishing channels. So the ingest is borrowed
from Scout and the funnel is borrowed from Reader, and neither is
copied.

WHAT IS REUSED, AND WHAT IS NOT. keyword_score, keyword_prefilter and
rank_and_cap come from papers/run.py unchanged — they are where
`min_per_digest` is honoured, and having two copies of that logic is
how the two would drift. The triage prompt and the renderer are local,
because Reader's are written for abstracts with arXiv ids and these
items are blog posts and release notes with ordinary URLs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.feeds import fetch, load_sources  # noqa: E402
from core.llm import LLM, OFFLINE  # noqa: E402
from core.spend import BudgetExceeded  # noqa: E402
from papers.run import (  # noqa: E402
    keyword_prefilter,
    rank_and_cap,
)
from telegram import api  # noqa: E402

FEEDS_PATH = REPO_ROOT / "feeds-security-intel.json"
PROFILE_PATH = REPO_ROOT / "config" / "security_profile.yaml"
BUDGET_PATH = REPO_ROOT / "config" / "security_budget.json"

PER_SOURCE_LIMIT = 25
KEYWORD_SURVIVOR_CAP = 60
TRIAGE_BATCH_SIZE = 20
DAILY_CAP = 10

# Wide enough for the slow sources — MITRE ATLAS revises a few times a
# year — and narrow enough that a prolific blog's back catalogue is not
# news. Without it the first run of any feed reads its whole archive:
# Embrace The Red alone carries 232 posts going back years, and they
# score well precisely because it is the best source here.
MAX_AGE_DAYS = 21

# One source may not take more than this many of the day's slots. The
# same prolific-source problem, at the other end of the funnel: on a
# first run without this, 8 of 10 picks came from one blog.
PER_SOURCE_CAP = 3


# --- fetch ---------------------------------------------------------------


def fetch_items() -> list[dict]:
    """Every in-scope source, failure-isolated, flattened to the dict
    shape Reader's funnel works on. A source that fails is one line on
    stderr, never an exit code: a dead scanner repo must not cost the
    morning's digest."""
    sources = [s for s in load_sources(FEEDS_PATH) if s.in_scope]
    print(f"  {len(sources)} source(s) in scope")
    items: list[dict] = []
    for source in sources:
        try:
            fetched = fetch(source, limit=PER_SOURCE_LIMIT)
        except Exception as exc:  # noqa: BLE001
            print(f"    {source.name}: fetch failed ({exc})", file=sys.stderr)
            continue
        for item in fetched:
            items.append({
                "id": item.id,
                "title": " ".join((item.title or "").split()),
                "abstract": " ".join((item.summary or "").split())[:2000],
                "link": item.url,
                "source": source.name,
                "published": item.published or "",
            })
    return items


def recent(items: list[dict], days: int = MAX_AGE_DAYS) -> list[dict]:
    """Drop anything older than `days`. An item with no usable date is
    KEPT — several of these sources are GitHub release feeds whose dates
    occasionally do not parse, and silently dropping a release because
    its timestamp was malformed is worse than showing it."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for item in items:
        stamp = item.get("published") or ""
        if not stamp:
            out.append(item)
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            out.append(item)
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            out.append(item)
    return out


def cap_per_source(picks: list[dict], cap: int = PER_SOURCE_CAP) -> list[dict]:
    """Keep the digest from becoming one blog's feed. Applied after
    ranking, so each source keeps its best items rather than its first."""
    seen: dict[str, int] = {}
    out = []
    for item in picks:
        name = item.get("source", "")
        if seen.get(name, 0) >= cap:
            continue
        seen[name] = seen.get(name, 0) + 1
        out.append(item)
    return out


def dedup(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = item["id"] or item["link"]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# --- triage --------------------------------------------------------------


TRIAGE_SYSTEM = """You triage security items for one engineer's daily \
reading digest. The corpus is AI/LLM security: attack writeups, scanner \
and guardrail releases, threat-matrix updates, advisories, standards.

Score each item 0-100 on how worth ten minutes it is TO SOMEONE WHO \
BUILDS AND RUNS LLM SYSTEMS.

Score HIGH: a concrete attack with a mechanism you could reproduce or \
defend against; a new class of vulnerability; an advisory against a \
package people actually run; a threat-matrix or standard revision that \
changes what you would check for.

Score LOW: version bumps, dependency updates, changelogs with no named \
capability, marketing, conference announcements, anything whose \
security content is a passing mention.

Be harsh. Most release notes are a 20. An item that merely mentions \
"security" is not a security item.

Return strict JSON: {"items": [{"id": "...", "bucket": "%BUCKETS%", \
"score": <0-100>, "one_line": "<one sentence: what it actually is, and \
why it matters>"}]}
one_line must state the substance, not restate the title."""


def triage_batch(llm: LLM, batch: list[dict], profile: dict) -> list[dict]:
    listing = "\n\n".join(
        f"id: {p['id']}\nsource: {p['source']}\n"
        f"bucket (pre-sorted, may be wrong): {p['bucket']}\n"
        f"title: {p['title']}\ntext: {p['abstract'][:1000]}"
        for p in batch
    )

    def offline_stub():
        return {"items": [
            {"id": p["id"], "bucket": p["bucket"],
             "score": min(90, 40 + p["keyword_score"] * 8),
             "one_line": p["title"][:140]}
            for p in batch
        ]}

    enum = "|".join(profile.get("buckets", {})) or "attacks"
    result = llm.json(
        listing,
        model="gpt-4o-mini",
        system=TRIAGE_SYSTEM.replace("%BUCKETS%", enum),
        offline=offline_stub if llm.offline else None,
        label="security-triage",
    )
    if not result or "items" not in result:
        return []
    by_id = {p["id"]: p for p in batch}
    out = []
    for row in result["items"]:
        base = by_id.get(row.get("id"))
        if not base:
            continue
        out.append({**base,
                    "bucket": row.get("bucket", base["bucket"]),
                    "score": float(row.get("score", 0)),
                    "one_line": str(row.get("one_line", "")).strip()})
    return out


def triage(llm: LLM, survivors: list[dict], max_calls: int, profile: dict) -> list[dict]:
    scored = []
    for start in range(0, len(survivors), TRIAGE_BATCH_SIZE):
        if start // TRIAGE_BATCH_SIZE >= max_calls:
            print(f"  security budget: stopped triage at {max_calls} calls "
                  f"({len(survivors) - start} items left unscored)", file=sys.stderr)
            break
        scored.extend(triage_batch(llm, survivors[start:start + TRIAGE_BATCH_SIZE], profile))
    return scored


# --- render + send -------------------------------------------------------


def render(picks: list[dict], total: int) -> str:
    if not picks:
        return f"Security — nothing cleared the bar today ({total} items seen)."
    counts: dict[str, int] = {}
    for p in picks:
        counts[p["bucket"]] = counts.get(p["bucket"], 0) + 1
    header = " ".join(f"{k.upper()} {v}" for k, v in counts.items())
    lines = [f"Security — {len(picks)} of {total} · {header}", ""]
    for i, p in enumerate(picks, 1):
        lines.append(f"{i}. [{p['bucket'].upper()}] {p['title']}")
        if p.get("one_line"):
            lines.append(f"   {p['one_line']}")
        lines.append(f"   {p['source']} · {p['link']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def send(text: str) -> bool:
    result = api.send(text)
    return bool(result and result.get("ok"))


# --- main ----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true",
                        help="actually send to Telegram")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--offline-llm", action="store_true",
                        help="deterministic triage, no API calls")
    args = parser.parse_args(argv)
    dry_run = not args.publish

    print(f"Security intel — {'DRY RUN, nothing will be sent' if dry_run else 'PUBLISHING FOR REAL'}")

    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))

    items = dedup(fetch_items())
    fresh = recent(items)
    print(f"  {len(items)} unique item(s), {len(fresh)} within {MAX_AGE_DAYS} days")
    items = fresh
    survivors = keyword_prefilter(items, profile, cap=KEYWORD_SURVIVOR_CAP)
    print(f"  {len(survivors)} survive the keyword filter (cap {KEYWORD_SURVIVOR_CAP})")

    try:
        llm = LLM(OFFLINE if args.offline_llm else None)
    except BudgetExceeded as exc:
        print(f"\n  SPEND CEILING — refused before starting: {exc}", file=sys.stderr)
        return 3

    try:
        scored = triage(llm, survivors, budget["max_llm_calls_per_run"], profile)
    except BudgetExceeded as exc:
        print(f"\n  SPEND CEILING — run aborted: {exc}", file=sys.stderr)
        if llm.guard is not None:
            from core import spend as spend_module
            spend_module.record_run(llm.guard, channel="security-intel", aborted=True)
        return 3
    finally:
        if llm.guard is not None and llm.guard.calls:
            print(f"  spend: {llm.guard.summary()}")

    if llm.guard is not None:
        from core import spend as spend_module
        spend_module.record_run(llm.guard, channel="security-intel")

    print(f"  {len(scored)} scored by triage ({llm.calls} model call(s))")
    picks = cap_per_source(rank_and_cap(scored, cap=DAILY_CAP * 3, profile=profile))[:DAILY_CAP]
    text = render(picks, total=len(items))
    print()
    print(text)

    if dry_run:
        print("[dry-run] not sent. Re-run with --publish to send for real.")
        return 0
    print("Sending to Telegram...")
    ok = send(text)
    print("sent." if ok else "send FAILED — see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
