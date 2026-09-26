#!/usr/bin/env python3
"""
Reader Phase 1 (build brief §9.11) — a disposable weekend prototype.

    python scripts/papers/run.py            [--dry-run] (default)
    python scripts/papers/run.py --publish   (actually sends to Telegram)
    python scripts/papers/run.py --offline-llm

Deliberately isolated from Scout (§9.2): the only two things imported from
the rest of this repo are telegram/api.py and core/llm.py, both named in
the brief as thin and stable enough to share. Everything else — feed
fetching, dedup, the keyword filter, the triage prompt — is written fresh
here rather than reusing core/feeds.py or core/classify.py, on purpose:
Reader answers "is this worth *my* ten minutes", Scout answers "is this
worth publishing to the world" (§9.1), and importing Scout's machinery
risks importing Scout's bar along with it.

Phase 1 has NO write path to content, the ledger, the budget files, or
interest_profile.yaml, and no persistent dedup — it re-reads the last 24h
of the combined feed every run and accepts the occasional repeat rather
than building a state branch before knowing the profile is any good
(§9.11's whole argument for why Phase 1 should be disposable).

NOTHING HERE SENDS A REAL TELEGRAM MESSAGE UNLESS --publish IS PASSED.
The default is always to print the digest and exit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import feedparser
import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.llm import LLM, OFFLINE  # noqa: E402
from core.spend import BudgetExceeded  # noqa: E402
from telegram import api  # noqa: E402

FEED_URL = "https://rss.arxiv.org/rss/cs.LG+cs.CL+cs.AI+cs.NE+stat.ML"
USER_AGENT = "SecureseinReader/0.1 (+https://securesein.github.io/)"
FEED_TIMEOUT = 25

PROFILE_PATH = REPO_ROOT / "config" / "papers_profile.yaml"
BUDGET_PATH = REPO_ROOT / "config" / "papers_budget.json"

TRIAGE_BATCH_SIZE = 20
KEYWORD_SURVIVOR_CAP = 85  # §9.4's 335 -> 85 step
DAILY_CAP = 12  # doubled from the Phase 1 default of 6 per owner request

DROP_ANNOUNCE_TYPES = {"replace", "replace-cross"}

ANNOUNCE_RE = re.compile(r"Announce Type:\s*([\w-]+)", re.IGNORECASE)
ID_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})")
ABSTRACT_RE = re.compile(r"Abstract:\s*(.*)", re.IGNORECASE | re.DOTALL)


# --- fetch -------------------------------------------------------------


def fetch_feed(url: str = FEED_URL) -> list[dict]:
    """One HTTP GET, parsed into plain dicts. Never raises — a failed
    fetch is a quiet, empty digest, not a crashed run (§9.1's asymmetry:
    a false negative here costs nothing, a crash costs a missed morning)."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=FEED_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  feed fetch failed: {exc}", file=sys.stderr)
        return []

    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries:
        raw = entry.get("summary", "") or entry.get("description", "")
        announce = ANNOUNCE_RE.search(raw)
        idm = ID_RE.search(entry.get("link", ""))
        abstract_m = ABSTRACT_RE.search(raw)
        if not idm:
            continue
        items.append({
            "id": idm.group(1),
            "title": (entry.get("title") or "").strip(),
            "abstract": (abstract_m.group(1).strip() if abstract_m else raw.strip()),
            "link": entry.get("link", ""),
            "announce_type": (announce.group(1).lower() if announce else "unknown"),
        })
    return items


# --- funnel steps --------------------------------------------------------


def dedup(items: list[dict]) -> list[dict]:
    """Bare arXiv ID, first occurrence wins. Cross-listings under the
    combined feed URL show up once per category, not once per paper —
    this collapses them (§9.3)."""
    seen: set[str] = set()
    out = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def drop_non_new(items: list[dict]) -> list[dict]:
    """§9.3's highest-value single filter: without it, a v2 re-enters the
    feed and Reader re-shows a paper it already sent."""
    return [i for i in items if i["announce_type"] not in DROP_ANNOUNCE_TYPES]


def load_profile(path: Path = PROFILE_PATH) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def keyword_score(item: dict, profile: dict) -> tuple[float, str | None]:
    """Deterministic, zero-cost prefilter (§9.4's 335 -> 85 step). Returns
    (score, best_bucket) or (0, None) if excluded or no bucket matched.
    This is the step that does most of the volume reduction, on purpose,
    before any model call happens."""
    text = f"{item['title']} {item['abstract']}".lower()

    for phrase in profile.get("exclude", []):
        if phrase.lower() in text:
            return 0.0, None

    best_score = 0.0
    best_bucket = None
    for bucket, spec in profile.get("buckets", {}).items():
        weight = spec.get("weight", 1.0)
        hits = sum(1 for kw in spec.get("keywords", []) if kw.lower() in text)
        score = hits * weight
        if score > best_score:
            best_score = score
            best_bucket = bucket

    # Downweight, don't drop: a domain-application paper ("LLM for
    # radiology reports") still matches a real bucket keyword and is
    # occasionally worth reading, it just shouldn't crowd out general
    # method papers the way it was. Unlike `exclude`, this never zeroes
    # the score or the bucket.
    penalize = profile.get("penalize", {})
    if best_bucket and any(kw.lower() in text for kw in penalize.get("keywords", [])):
        best_score *= penalize.get("factor", 1.0)

    return best_score, best_bucket


def keyword_prefilter(items: list[dict], profile: dict, cap: int = KEYWORD_SURVIVOR_CAP) -> list[dict]:
    scored = []
    for item in items:
        score, bucket = keyword_score(item, profile)
        if score > 0 and bucket:
            scored.append({**item, "keyword_score": score, "bucket": bucket})
    scored.sort(key=lambda i: i["keyword_score"], reverse=True)
    return scored[:cap]


TRIAGE_SYSTEM = """You triage arXiv abstracts for a personal reading digest, not a \
publication. Score each paper 0-100 on how worth a technical reader's ten minutes \
it is, independent of the bucket it was pre-sorted into (you may recategorize).
Favor: incremental-but-real technical contributions, mechanism explained clearly, \
code or reproducibility mentioned, results that would change how the reader thinks \
about the bucket topic.
Penalize: pure theory with no learning system in view, narrow domain application \
papers, "we fine-tuned X on Y" with no methodological novelty, surveys (score low \
regardless of quality -- surveys go in a separate weekly digest, not here). \
Clinical/medical/healthcare applications of general ML/LLM techniques are \
over-represented in the raw feed relative to how novel they usually are -- score \
these lower unless the methodological contribution itself (not just the domain) \
is genuinely novel.
Return strict JSON: {"papers": [{"id": "...", "bucket": "llm|neural_nets|rl", \
"score": <0-100>, "one_line": "<one sentence, what it actually claims>"}]}
one_line must be a genuine claim from the abstract, not a restated title."""


def triage_batch(llm: LLM, batch: list[dict]) -> list[dict]:
    listing = "\n\n".join(
        f"id: {p['id']}\nbucket (pre-sorted, may be wrong): {p['bucket']}\n"
        f"title: {p['title']}\nabstract: {p['abstract'][:1200]}"
        for p in batch
    )

    def offline_stub():
        # Deterministic stand-in: keeps the keyword bucket/score, no model
        # call. Used by --offline-llm and whenever OPENAI_API_KEY is unset.
        return {"papers": [
            {"id": p["id"], "bucket": p["bucket"], "score": min(90, 40 + p["keyword_score"] * 8),
             "one_line": p["title"][:140]}
            for p in batch
        ]}

    result = llm.json(
        listing,
        model="gpt-4o-mini",
        system=TRIAGE_SYSTEM,
        offline=offline_stub if llm.offline else None,
        label="papers-triage",
    )
    if not result or "papers" not in result:
        return []
    by_id = {p["id"]: p for p in batch}
    out = []
    for row in result["papers"]:
        base = by_id.get(row.get("id"))
        if not base:
            continue  # the model named an id we never sent it -- drop, don't guess
        out.append({**base, **row})
    return out


def triage(llm: LLM, survivors: list[dict], max_calls: int) -> list[dict]:
    scored = []
    for start in range(0, len(survivors), TRIAGE_BATCH_SIZE):
        if start // TRIAGE_BATCH_SIZE >= max_calls:
            print(f"  papers budget: stopped triage at {max_calls} calls "
                  f"({len(survivors) - start} abstracts left unscored this run)",
                  file=sys.stderr)
            break
        batch = survivors[start:start + TRIAGE_BATCH_SIZE]
        scored.extend(triage_batch(llm, batch))
    return scored


def rank_and_cap(scored: list[dict], cap: int = DAILY_CAP) -> list[dict]:
    scored = sorted(scored, key=lambda p: p.get("score", 0), reverse=True)
    return scored[:cap]


# --- render + send -------------------------------------------------------


def render(picks: list[dict], total_new: int) -> str:
    if not picks:
        return f"Papers — nothing cleared the bar today ({total_new} new, all below threshold)."

    by_bucket: dict[str, int] = {}
    for p in picks:
        by_bucket[p["bucket"]] = by_bucket.get(p["bucket"], 0) + 1
    bucket_line = " ".join(f"{k.upper()} {v}" for k, v in by_bucket.items())

    lines = [f"Papers — {len(picks)} of {total_new} new · {bucket_line}", ""]
    for i, p in enumerate(picks, 1):
        lines.append(f"{i}. [{p['bucket'].upper()}] {p['title']}")
        lines.append(f"   {p.get('one_line', '')}")
        lines.append(f"   arxiv.org/abs/{p['id']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def send(text: str) -> bool:
    """Reuses telegram/api.send() verbatim (§9.2 point 5: one of the two
    modules explicitly allowed to be shared). It reads TELEGRAM_CHAT_ID
    from the environment with no knowledge of which chat that is --
    papers.yml sets that env var to TELEGRAM_PAPERS_CHAT_ID's value for
    this step specifically, so the SAME function safely targets a
    DIFFERENT chat without api.py knowing Reader exists."""
    result = api.send(text)
    return bool(result and result.get("ok"))


# --- entrypoint ------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_true", default=None)
    group.add_argument("--publish", dest="dry_run", action="store_false")
    parser.add_argument("--offline-llm", action="store_true")
    args = parser.parse_args(argv)
    dry_run = True if args.dry_run is None else args.dry_run

    profile = load_profile()
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))

    print("Reader (Phase 1) — " + ("DRY RUN, nothing will be sent" if dry_run else "PUBLISHING FOR REAL"))

    raw = fetch_feed()
    print(f"  fetched {len(raw)} raw entries")
    items = dedup(raw)
    print(f"  {len(items)} unique papers after id-dedup")
    items = drop_non_new(items)
    print(f"  {len(items)} genuinely new/cross after dropping replace(-cross)")

    survivors = keyword_prefilter(items, profile)
    print(f"  {len(survivors)} survive the keyword prefilter (cap {KEYWORD_SURVIVOR_CAP})")

    # The ceilings apply here automatically (LLM builds its own guard),
    # but this entrypoint has to record what it spent or the day, week
    # and month windows would never see it — every later run would then
    # be measuring against a total that silently excludes this one.
    from core import spend as spend_module

    try:
        llm = LLM(OFFLINE if args.offline_llm else None)
    except BudgetExceeded as exc:
        print(f"\n  SPEND CEILING — run refused before it started: {exc}", file=sys.stderr)
        return 3

    try:
        scored = triage(llm, survivors, max_calls=budget["max_llm_calls_per_run"])
    except BudgetExceeded as exc:
        print(f"\n  SPEND CEILING — run aborted: {exc}", file=sys.stderr)
        spend_module.record_run(llm.guard, channel="papers", aborted=True)
        return 3
    finally:
        if llm.guard is not None and llm.guard.calls:
            print(f"  spend: {llm.guard.summary()}")

    spend_module.record_run(llm.guard, channel="papers")
    print(f"  {len(scored)} scored by triage ({llm.calls} model call(s))")

    picks = rank_and_cap(scored)
    text = render(picks, total_new=len(items))
    print()
    print(text)

    if not dry_run:
        print("Sending to Telegram...")
        ok = send(text)
        print("sent." if ok else "send FAILED — see above.")
    else:
        print("[dry-run] not sent. Re-run with --publish to send for real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
