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
        # Compared against the RANGE of the independent readings, not
        # against each one in turn.
        #
        # Epoch runs one model at several reasoning efforts and stores
        # each as its own record, so glm-5-2 on GPQA Diamond is 91.86 at
        # max effort, 87.88 at low and 71.21 at none. A vendor quoting
        # 91.2 is quoting its best configuration and agrees with the
        # max-effort run to within 0.7. Comparing the claim to each
        # record in turn fires on the `none` run and reports "a 20.0
        # point gap", which is a false accusation against a named
        # company — and it would have fired on the very first run of
        # this channel for three separate vendors.
        #
        # A claim landing anywhere inside the spread an independent
        # evaluator already measured is a vendor quoting its best
        # configuration, which is normal and not a story. Only a claim
        # outside that spread is one.
        by_model: dict[str, list[tuple[str, dict]]] = {}
        for entry_id, record in independent:
            by_model.setdefault(record["model"], []).append((entry_id, record))

        for model_id, (claim_id, claim_record) in vendor_claims.items():
            readings = [
                pair
                for pair in by_model.get(model_id, [])
                # An Elo and a percentage are not comparable.
                if pair[1]["unit"] == claim_record["unit"]
            ]
            if not readings:
                continue
            if claim_id not in new_records and not any(
                entry_id in new_records for entry_id, _ in readings
            ):
                continue  # already reported on a previous run

            claim_value = float(claim_record["value"])
            lowest = min(readings, key=lambda pair: float(pair[1]["value"]))
            highest = max(readings, key=lambda pair: float(pair[1]["value"]))
            low, high = float(lowest[1]["value"]), float(highest[1]["value"])

            if claim_value > high:
                gap, nearest = claim_value - high, highest
            elif claim_value < low:
                gap, nearest = low - claim_value, lowest
            else:
                continue  # inside the independently measured spread
            if gap < gap_pp:
                continue

            measured = (
                f"{low}" if lowest[0] == highest[0]
                else f"{low} to {high} across {len(readings)} runs"
            )
            # Both edges are cited, not just the nearest: the detail
            # names both numbers and G5 rejects a roundup citing a
            # figure that is not one of the referenced measurements.
            refs = [claim_id, nearest[0], lowest[0], highest[0]]
            fired.append(
                _fired(
                    "vendor_vs_thirdparty_gap",
                    weights,
                    f"{model_id} on {benchmark.name}: "
                    f"{claim_record['evaluator']} claims {claim_record['value']}, "
                    f"{nearest[1]['evaluator']} measured {measured} — the claim is "
                    f"{gap:.1f} points outside the independently measured range",
                    list(dict.fromkeys(refs)),
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
