"""
Vendor-published benchmark claims, via Hugging Face Community Evals.

This is the missing half of the /benchmarks table. Until now the
collection held 1325 measurements of which exactly **two** were
`measuredBy: vendor`, which meant the one thing the page is built to
show — a vendor's own claim sitting next to an independent measurement
of the same model on the same benchmark — had nothing to show, and
`vendor_vs_thirdparty_gap`, the highest-weighted trigger in
config/benchmarks.json, could never fire.

Hugging Face exposes, per benchmark dataset, an aggregate of the scores
that model authors publish in their own repositories:

    https://huggingface.co/api/datasets/<dataset>/leaderboard

Tokenless, public JSON, no API key, and — importantly for this
pipeline's cost ceilings — **no model call anywhere in this file**.

WHAT COUNTS AS A VENDOR CLAIM. The endpoint aggregates several kinds of
row and only one of them is a vendor claim, so the filter is strict and
lives in `_is_vendor_claim`:

  - an open community pull request is a proposal, not a published
    claim                                     -> `pullRequest` present
  - a score sourced from somewhere other than the model repo is not
    self-reported                             -> `source.isExternal`
  - a score published in a *re-upload* of someone else's weights (the
    quantisation and conversion repos: RedHatAI/*, exolabs/*, and so
    on) is not the original vendor speaking
                              -> `source.url` != the model's own repo

Note what the filter deliberately does NOT do: judge whether the claim
is plausible. On 2026-10-02 the GPQA board was topped by
`FINAL-Bench/Darwin-180B-RSI` at 94.44% — an unknown organisation
claiming, in its own model card, to beat every frontier lab. It passes
every provenance test above, because it genuinely is a self-published
claim. Two existing mechanisms contain it and neither is weakened here:

  1. models.json is a CLOSED vocabulary. Darwin is not in it, so the
     row is parked in state/unresolved_models.jsonl for a human and
     never reaches the collection. This is the reason the registry must
     never be auto-populated.
  2. benchmark_triggers.evaluate() excludes `measuredBy: vendor` rows
     from `new_leader` outright — "a vendor's own claim does not get to
     crown itself". A self-published number can therefore never make
     this channel announce a new leader.

CONDITIONS. Every vendor row observed carried `notes: null` — no shot
count, no harness, no reasoning effort. That is itself worth recording
rather than hiding, because the contrast the table exists to draw is
between a number with stated conditions and a number without, so
`conditions.notes` says so explicitly. It is also why the digest stays
stable across runs: upsert identity is (benchmark, model, evaluator,
conditions digest), so a deterministic conditions blob makes a repeat
run a clean no-op instead of a duplicate.

MEASURED-AT. The endpoint carries no date per row. The model's
`releasedAt` from the registry is used, because a model card's score is
a property of that release; today's date is the fallback. The date is
not part of upsert identity, so this choice cannot create duplicates —
it only decides the filename of a record the first time it is written.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date

import requests

HUB_API = "https://huggingface.co/api/datasets/{dataset}/leaderboard"
HUB_MODEL_URL = "https://huggingface.co/{model_id}"
PUBLISHER = "Hugging Face Community Evals"
LICENSE = (
    "Each row is a score the model's own organisation published in its "
    "Hugging Face model card; attribution is the per-row sourceUrl."
)
TIMEOUT = 25
USER_AGENT = "securesein-pipeline/1.0 (+https://securesein.github.io)"


@dataclass(frozen=True)
class Board:
    """One tracked benchmark and the HF dataset whose board carries it."""

    slug: str          # must exist in benchmarks.json
    dataset: str       # the HF dataset id
    note: str = ""


# Deliberately a short list. Each entry was checked on 2026-10-02 for
# whether it can actually produce a comparison, because a vendor claim
# for a model nobody independent has measured is a number with nothing
# to sit beside:
#
#   gpqa-diamond         27 claims -> 10 resolve -> 9 comparable to Epoch
#   swe-bench-verified   16 claims ->  4 resolve -> 1 comparable
#   hle                  23 claims -> 16 resolve -> 0 comparable
#
# HLE is included even with zero overlap today: the claims resolve, so
# they populate the vendor column of the table, and Epoch's HLE coverage
# is closed-frontier models while these are open-weights labs — the two
# sets are expected to converge rather than stay disjoint.
#
# MMLU-Pro is deliberately absent. Its board yielded 4 claims, none of
# which resolved, and Epoch carries no MMLU-Pro rows at all, so it can
# produce neither a comparison nor a populated column.
BOARDS = (
    Board("gpqa-diamond", "Idavidrein/gpqa",
          "Best overlap with Epoch; where the gap trigger can first fire."),
    Board("swe-bench-verified", "SWE-bench/SWE-bench_Verified",
          "Agent harness dominates this score and vendors rarely state it."),
    Board("hle", "cais/hle",
          "No overlap with Epoch yet; populates the vendor column."),
)


def _is_vendor_claim(row: dict) -> bool:
    """See the module docstring. Provenance only — never plausibility."""
    if row.get("pullRequest") is not None:
        return False
    source = row.get("source") or {}
    if source.get("isExternal"):
        return False
    model_id = (row.get("modelId") or "").strip()
    if not model_id:
        return False
    return source.get("url", "") == HUB_MODEL_URL.format(model_id=model_id)


def _value(raw, unit: str) -> float | None:
    """Boards mix percentages (94.44) and fractions (0.9444) for the
    same metric, so a bare number is ambiguous below 1.0. Treating
    <= 1 as a fraction is safe here: every benchmark on these boards is
    scored out of 100 and a genuine 1% would be an outlier far below
    anything on the board."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if unit == "percent":
        if value <= 1.0:
            value *= 100
        return round(value, 2)
    return round(value, 3)


def _conditions(row: dict) -> dict:
    """Deterministic, so a repeat run is a no-op rather than a duplicate."""
    notes = (row.get("notes") or "").strip()
    if notes:
        return {"notes": f"Self-reported in the model card: {notes}"}
    return {"notes": "Self-reported in the model card; conditions not stated"}


def _fetch(dataset: str) -> list[dict]:
    response = requests.get(
        HUB_API.format(dataset=dataset),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def collect(registry, ctx=None) -> tuple[list[dict], list[dict]]:
    """Normalise every tracked board into collection-shaped records.

    Returns (measurements, unresolved), matching the epoch adapter's
    contract. A board that fails to fetch is reported and skipped — one
    dead endpoint must not cost the others, and benchmarks.py turns an
    exception into state/adapter_failures.jsonl rather than an exit code.
    """
    measurements: list[dict] = []
    unresolved: list[dict] = []
    seen_unresolved: set[tuple[str, str]] = set()
    today = date.today().isoformat()

    for board in BOARDS:
        benchmark = registry.resolve_benchmark(board.slug)
        if benchmark is None:
            # Slug not in the closed vocabulary: drop, never invent.
            continue
        try:
            rows = _fetch(board.dataset)
        except Exception as exc:  # noqa: BLE001 — one board, not the run
            print(f"    hf_leaderboard {board.slug}: fetch failed ({exc}) — skipped.",
                  file=sys.stderr)
            continue

        claims = [row for row in rows if _is_vendor_claim(row)]
        print(f"    hf_leaderboard {board.slug}: {len(rows)} row(s), "
              f"{len(claims)} vendor claim(s) after the provenance filter")

        for row in claims:
            model_id = row["modelId"]
            organisation, _, short_name = model_id.partition("/")
            model = registry.resolve_model(short_name or model_id)
            if model is None:
                key = (board.slug, model_id)
                if key not in seen_unresolved:
                    seen_unresolved.add(key)
                    unresolved.append(
                        {
                            "name": short_name or model_id,
                            "source": "hf_leaderboard",
                            "benchmark": board.slug,
                            "organization": organisation,
                            "seenAt": today,
                        }
                    )
                continue

            value = _value(row.get("value"), benchmark.unit)
            if value is None:
                continue

            measurements.append(
                {
                    "model": model.id,
                    "vendor": model.vendor,
                    "benchmark": benchmark.slug,
                    "metric": benchmark.metric,
                    "value": value,
                    "unit": benchmark.unit,
                    "measuredBy": "vendor",
                    # Distinct from Epoch's evaluator on purpose: upsert
                    # identity includes the evaluator, so the vendor's
                    # claim and the independent run are two rows, which
                    # is what lets the gap trigger see both.
                    "evaluator": f"Vendor model card ({organisation})",
                    "conditions": _conditions(row),
                    "measuredAt": model.released_at or today,
                    "sourceUrl": (row.get("source") or {}).get(
                        "url", HUB_MODEL_URL.format(model_id=model_id)
                    ),
                    "publisher": PUBLISHER,
                    "license": LICENSE,
                    "attribution": f"{organisation}, via {PUBLISHER}",
                }
            )

    return measurements, unresolved
