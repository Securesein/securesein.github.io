#!/usr/bin/env python3
"""
One-time backfill: vendor-claimed benchmark numbers that are already
sitting in the News archive, written into the measurements collection
as `measuredBy: "vendor"` records.

    python3 scripts/backfill_vendor_benchmarks.py [--write]

Without --write it reports and changes nothing.

Why this exists: §6.4 says any benchmark number appearing in a release
post must also be written to the collection, because "a number that
exists only in prose is not allowed" — the two channels share one
factual substrate. The archive predates that rule and contains vendor
claims in prose only. Backfilling them is what makes the
vendor-versus-third-party contrast on /benchmarks/ possible for models
the site has already covered.

Three rules, and all three are about not inventing anything:

  1. **The benchmark must be in /benchmarks.json.** An unknown name is
     dropped and reported, never added to the registry. "ARC-AGI-3" and
     "FrontierCode 1.1" are in the archive; neither is tracked, so
     neither is ingested. Same rule as topics.
  2. **The model must resolve in /models.json.** No auto-registration.
  3. **The number must be attributable.** The post must carry a
     `source`, and the sentence must actually attribute the figure to
     the vendor ("OpenAI claims...", "according to Google") or come
     from the vendor's own publication. A number a Scout post states
     flatly, with no attribution, is not a vendor claim — it is a
     sentence, and it is skipped.

Everything skipped is printed with its reason, so the gap between
"numbers in the archive" and "numbers in the collection" is visible
rather than silent.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.constants import BLOG_DIR  # noqa: E402
from core.frontmatter import read_frontmatter  # noqa: E402
from core.measurements import Store  # noqa: E402
from core.registry import load_registry  # noqa: E402

# How each tracked benchmark is actually spelled in prose. Kept here
# rather than in benchmarks.json so the registry stays the vocabulary
# the brief specifies, with no extra fields; every consumer that has to
# recognise a benchmark by name carries its own mapping (the Epoch
# adapter does the same thing with CSV filenames).
SPELLINGS = {
    "gpqa-diamond": r"GPQA(?:\s+Diamond)?",
    "frontiermath": r"FrontierMath(?:\s+Tier\s*\d)?",
    "swe-bench-verified": r"SWE[-\s]?bench(?:\s+Verified)?",
    "terminal-bench": r"Terminal[-\s]?Bench",
    "arc-agi-2": r"ARC[-\s]?AGI[-\s]?2",
    "livebench": r"LiveBench",
    "aider-polyglot": r"Aider(?:\s+Polyglot)?",
    "hle": r"(?:Humanity'?s\s+Last\s+Exam|\bHLE\b)",
    "mmlu-pro": r"MMLU[-\s]?Pro",
    "lmarena-text-elo": r"LMArena|Chatbot\s+Arena",
    "livecodebench": r"LiveCodeBench",
    "osworld": r"OSWorld",
}

# Names that look like benchmarks and are not tracked. Listed so the
# report can say "dropped, not tracked" instead of saying nothing.
UNTRACKED = re.compile(
    r"\b(ARC[-\s]?AGI[-\s]?3|FrontierCode[\s\d.]*|DeepSWE[\s\w.]*|GDP\.pdf|"
    r"SkillsBench|ExploitGym|ETHICS|Social-Chem-101|TruthfulQA|ImageNet|"
    r"MMLU(?![-\s]?Pro))\b",
    re.I,
)

ATTRIBUTION = re.compile(
    r"\b(claims?|claimed|reports?|reported|according to|says?|said|"
    r"announced|states?|per\s+the\s+(?:model|system)\s+card|"
    r"vendor[-\s]reported)\b",
    re.I,
)

# A percentage, or a bare decimal used as a score.
NUMBER = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%|\b(\d{1,3}\.\d)\b")


def sentences(text: str) -> list[str]:
    body = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+", body)


def find_claims(post_text: str, data: dict, registry) -> tuple[list[dict], list[str]]:
    """(records, skipped-with-reason) for one post."""
    records: list[dict] = []
    skipped: list[str] = []

    source = data.get("source") or {}
    published = str(data.get("pubDate", ""))[:10]
    subject = f"{data.get('title', '')} {data.get('description', '')}"
    publisher = source.get("publisher", "")
    url = source.get("url", "")

    for sentence in sentences(post_text):
        untracked = UNTRACKED.findall(sentence)
        for name in untracked:
            if NUMBER.search(sentence):
                skipped.append(
                    f'"{name.strip()}" is not in benchmarks.json — dropped, '
                    f"never invented"
                )

        for slug, pattern in SPELLINGS.items():
            hits = list(re.finditer(pattern, sentence, re.I))
            if not hits:
                continue
            numbers = [m.group(1) or m.group(2) for m in NUMBER.finditer(sentence)]
            if not numbers:
                skipped.append(f"{slug}: named but with no figure in the sentence")
                continue
            if not url:
                skipped.append(f"{slug}: the post has no `source` to attribute to")
                continue
            if not ATTRIBUTION.search(sentence):
                skipped.append(
                    f"{slug}: figure stated without attributing it to anyone — "
                    f"not a vendor claim"
                )
                continue

            # The sentence names the claim; the headline names the
            # subject. A claim sentence almost always mentions the
            # PREVIOUS model too ("47% faster than GPT-5.6 Sol"), so
            # falling back to the title and lede rather than to the body
            # is what keeps the figure attached to the right model.
            model = _model_in(sentence, registry) or _model_in(subject, registry)
            if model is None:
                skipped.append(f"{slug}: no model in this sentence resolves in models.json")
                continue

            benchmark = registry.resolve_benchmark(slug)
            # Several benchmarks in one sentence and several numbers in
            # the same order is the shape these claims actually take
            # ("FrontierMath Tier 4 and ARC-AGI-3, achieving 98% and
            # 99.9% respectively") — so pair them positionally, and only
            # when the counts line up. If they do not, the pairing is a
            # guess and a guessed benchmark score is exactly what this
            # whole channel exists to prevent.
            named = _all_named(sentence)
            if len(named) != len(numbers):
                skipped.append(
                    f"{slug}: {len(named)} benchmark name(s) and {len(numbers)} "
                    f"figure(s) in one sentence — cannot pair them safely"
                )
                continue
            try:
                value = float(numbers[named.index(slug)])
            except (ValueError, IndexError):
                skipped.append(f"{slug}: could not read the figure")
                continue

            variant = hits[0].group(0)
            records.append(
                {
                    "model": model.id,
                    "vendor": model.vendor,
                    "benchmark": benchmark.slug,
                    "metric": benchmark.metric,
                    "value": value,
                    "unit": benchmark.unit,
                    "measuredBy": "vendor",
                    "evaluator": _vendor_label(model.vendor, publisher),
                    "conditions": {
                        "notes": (
                            f"Vendor claim as stated in “{variant}”. Conditions not "
                            f"published with the figure; recorded from the "
                            f"announcement rather than from a run."
                        )
                    },
                    "measuredAt": published,
                    "sourceUrl": url,
                    "publisher": publisher or "Unknown",
                }
            )
    return records, skipped


def _all_named(sentence: str) -> list[str]:
    """Every tracked benchmark named in this sentence, in the order they
    appear — which is the order the figures come in."""
    found = []
    for slug, pattern in SPELLINGS.items():
        match = re.search(pattern, sentence, re.I)
        if match:
            found.append((match.start(), slug))
    # An untracked name still occupies a slot in "A and B ... X and Y",
    # so it has to be counted or the pairing shifts.
    for match in UNTRACKED.finditer(sentence):
        found.append((match.start(), f"__untracked__{match.start()}"))
    return [slug for _, slug in sorted(found)]


def _model_in(text: str, registry):
    """Longest registry name wins; ties go to the one that appears
    first. Shared with the release classifier precisely so the two
    cannot disagree about which model a sentence is about."""
    from core.classify import _first_known_model

    return _first_known_model(text, registry)


VENDOR_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google DeepMind",
    "meta": "Meta AI",
    "microsoft": "Microsoft",
    "mistral": "Mistral AI",
    "nvidia": "NVIDIA",
    "deepseek": "DeepSeek",
    "alibaba": "Alibaba",
    "xai": "xAI",
}


def _vendor_label(vendor: str, publisher: str) -> str:
    return VENDOR_LABELS.get(vendor, publisher or vendor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="actually write the records")
    args = parser.parse_args()

    registry = load_registry()
    all_records: list[dict] = []
    report: list[str] = []

    for path in sorted(BLOG_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        data = read_frontmatter(path)
        body = text.split("---", 2)[-1]
        records, skipped = find_claims(body, data, registry)
        if records or skipped:
            report.append(f"\n{path.name}")
            for record in records:
                report.append(
                    f"  + {record['benchmark']:<20} {record['value']:>6}"
                    f"{'%' if record['unit'] == 'percent' else ''}  "
                    f"{record['model']}  (vendor: {record['evaluator']})"
                )
            for reason in dict.fromkeys(skipped):
                report.append(f"  - {reason}")
        all_records.extend(records)

    print("\n".join(report) or "Nothing found.")
    print(f"\n{len(all_records)} vendor claim(s) groundable in the archive.")

    store = Store(dry_run=not args.write)
    summary = store.upsert(all_records)
    print(f"upsert: {summary}")
    store.save()
    if not args.write:
        print("\nNothing written. Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
