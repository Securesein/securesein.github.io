"""
Roundup triggers for the Benchmarks channel (brief §7.3).

A run that ingests measurements and writes no post is the normal case.
A roundup happens when the data does something worth a paragraph, and
"worth a paragraph" is five specific events with weights, not a model's
opinion:

  new_leader                        4   someone took the top of a board
  new_top5_entrant                  2   a model arrived in the top five
  vendor_vs_thirdparty_gap          4   an independent run disagrees
                                        with the vendor's own claim by
                                        at least the configured margin
  benchmark_erratum_or_retraction   5   a number was withdrawn
  first_measurement_of_tier1_model  2   a frontier model got measured

`vendor_vs_thirdparty_gap` is the one that justifies the whole channel.
A leaderboard can tell you who is on top; only a tracker that keeps the
vendor's own number next to an independent one can tell you the two
disagree. It is never suppressed for being unflattering to a vendor.

Triggers are evaluated against what a run just changed, so the same
fact cannot fire on every subsequent run: `new_leader` looks only at
measurements written in this run, and the gap check only at pairs where
one side is new.
"""

from __future__ import annotations

import json

from core.constants import CONFIG_DIR
from core.measurements import Store
from core.registry import load_registry

CONFIG_FILE = CONFIG_DIR / "benchmarks.json"


def load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def _fired(name: str, weights: dict, detail: str, refs: list[str]) -> dict:
    return {"trigger": name, "weight": weights[name], "detail": detail, "refs": refs}


def evaluate(ctx, store: Store, config: dict | None = None) -> list[dict]:
    """Everything that fired because of THIS run's new measurements."""
    config = config or load_config()
    weights = config["triggers"]
    registry = load_registry()
    tier1 = set(config.get("tier1_vendors", []))
    gap_pp = float(config.get("vendor_gap_threshold_pp", 5))

    new_records: dict[str, dict] = dict(getattr(store, "pending", {}))
    if not new_records:
        return []

    # The state of the world after this run, superseded records dropped.
    everything: dict[str, dict] = {**store.existing, **new_records}
    superseded = {r.get("supersedes") for r in everything.values() if r.get("supersedes")}
    current = {k: v for k, v in everything.items() if k not in superseded}

    fired: list[dict] = []
    by_benchmark: dict[str, list[tuple[str, dict]]] = {}
    for entry_id, record in current.items():
        by_benchmark.setdefault(record["benchmark"], []).append((entry_id, record))

    seen_models_before = {
        r["model"] for k, r in store.existing.items() if k not in superseded
    }

    for slug, rows in by_benchmark.items():
        benchmark = registry.resolve_benchmark(slug)
        if benchmark is None:
            continue
        # Only independent readings decide a leaderboard. A vendor's own
        # claim sits in the table beside them; it does not get to crown
        # itself.
        independent = [
            (entry_id, record)
            for entry_id, record in rows
            if record["measuredBy"] != "vendor"
        ]
        if not independent:
            continue
        independent.sort(
            key=lambda pair: pair[1]["value"], reverse=benchmark.higher_is_better
        )

        leader_id, leader = independent[0]
        if leader_id in new_records:
            fired.append(
                _fired(
                    "new_leader",
                    weights,
                    f"{leader['model']} tops {benchmark.name} at "
                    f"{leader['value']}{'%' if leader['unit'] == 'percent' else ''} "
                    f"({leader['evaluator']})",
                    [leader_id],
                )
            )
        for entry_id, record in independent[1:5]:
            if entry_id in new_records:
                fired.append(
                    _fired(
                        "new_top5_entrant",
                        weights,
                        f"{record['model']} entered the top five on {benchmark.name}",
                        [entry_id],
                    )
                )

        # The gap check: a vendor claim and an independent run for the
        # same model on the same benchmark, disagreeing by enough to
        # matter.
        vendor_claims = {
            record["model"]: (entry_id, record)
            for entry_id, record in rows
            if record["measuredBy"] == "vendor"
        }
        for entry_id, record in independent:
            claim = vendor_claims.get(record["model"])
            if claim is None:
                continue
            claim_id, claim_record = claim
            if entry_id not in new_records and claim_id not in new_records:
                continue  # already reported on a previous run
            if record["unit"] != claim_record["unit"]:
                continue  # an Elo and a percentage are not comparable
            gap = abs(float(claim_record["value"]) - float(record["value"]))
            if gap >= gap_pp:
                fired.append(
                    _fired(
                        "vendor_vs_thirdparty_gap",
                        weights,
                        f"{record['model']} on {benchmark.name}: "
                        f"{claim_record['evaluator']} claims "
                        f"{claim_record['value']}, {record['evaluator']} measured "
                        f"{record['value']} — a {gap:.1f} point gap",
                        [claim_id, entry_id],
                    )
                )

    # A frontier model being measured for the first time is worth a
    # sentence even when it does not top anything.
    for entry_id, record in new_records.items():
        if record["model"] in seen_models_before:
            continue
        if record["vendor"] not in tier1:
            continue
        fired.append(
            _fired(
                "first_measurement_of_tier1_model",
                weights,
                f"first tracked measurement of {record['model']}",
                [entry_id],
            )
        )
        seen_models_before.add(record["model"])

    return fired


def total_weight(fired: list[dict]) -> int:
    return sum(int(t["weight"]) for t in fired)


def should_write_roundup(fired: list[dict], config: dict | None = None) -> bool:
    config = config or load_config()
    return total_weight(fired) >= int(config["threshold"])
