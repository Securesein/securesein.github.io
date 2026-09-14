"""
The measurements collection: the upsert rules, the closed vocabularies,
and the two things that must never happen — a model invented into the
registry, and a number whose conditions were thrown away.

No network: the Epoch adapter is exercised against the cached bundle
when one is present and skipped cleanly when it is not, so this suite
runs the same on a laptop with no internet as it does in CI.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.adapters import epoch  # noqa: E402
from core.measurements import Store, conditions_digest, identity, measurement_id  # noqa: E402
from core.registry import effort_of, load_registry, normalise  # noqa: E402

COLLECTION = REPO_ROOT / "src" / "content" / "benchmarks"


def _record(**overrides) -> dict:
    base = {
        "model": "gpt-6-astra",
        "vendor": "openai",
        "benchmark": "gpqa-diamond",
        "metric": "accuracy",
        "value": 95.77,
        "unit": "percent",
        "measuredBy": "thirdparty",
        "evaluator": "Epoch AI",
        "harness": "inspect",
        "conditions": {"shots": 0, "tools": False, "reasoningEffort": "high"},
        "measuredAt": "2026-08-30",
        "sourceUrl": "https://epoch.ai/benchmarks",
        "publisher": "Epoch AI",
    }
    base.update(overrides)
    return base


# --- identity --------------------------------------------------------


def test_conditions_are_part_of_a_measurements_identity():
    """The documented departure from §4's literal id format, and the
    reason for it: Epoch runs one model on one benchmark on one day at
    five reasoning efforts. Under the literal scheme four of the five
    silently overwrite the fifth, throwing away exactly the distinction
    the channel exists for."""
    high = _record(conditions={"shots": 0, "tools": False, "reasoningEffort": "high"})
    none = _record(
        value=82.93, conditions={"shots": 0, "tools": False, "reasoningEffort": "none"}
    )
    assert measurement_id(high) != measurement_id(none)
    assert identity(high) != identity(none)
    # ...and the same run described twice is still one identity.
    reordered = _record(conditions={"reasoningEffort": "high", "tools": False, "shots": 0})
    assert identity(high) == identity(reordered)
    assert conditions_digest(high["conditions"]) == conditions_digest(reordered["conditions"])


def test_empty_and_absent_conditions_agree():
    assert conditions_digest({"notes": "", "shots": None}) == conditions_digest({})


# --- the upsert rules (§7.2 step 3) ---------------------------------


def _store() -> Store:
    directory = Path(tempfile.mkdtemp()) / "benchmarks"
    return Store(directory=directory, dry_run=False)


def test_identical_measurement_is_a_no_op():
    store = _store()
    store.upsert([_record()])
    store.save()

    again = Store(directory=store.directory, dry_run=False)
    summary = again.upsert([_record()])
    assert summary["new"] == 0
    assert summary["unchanged"] == 1


def test_same_key_new_value_supersedes_rather_than_overwrites():
    """The old reading stays on the record. That a number moved is
    itself a story, and an overwrite would delete it."""
    store = _store()
    store.upsert([_record()])
    store.save()
    old_id = store.written[0]

    again = Store(directory=store.directory, dry_run=False)
    summary = again.upsert([_record(value=91.0, measuredAt="2026-09-10")])
    again.save()
    assert summary["new"] == 1
    assert summary["superseded"] == 1

    new_id = again.written[0]
    written = json.loads((store.directory / f"{new_id}.json").read_text())
    assert written["supersedes"] == old_id
    assert (store.directory / f"{old_id}.json").exists(), "the old reading is kept"


def test_new_key_is_a_new_record():
    store = _store()
    summary = store.upsert([_record(), _record(benchmark="hle", value=46.5)])
    assert summary["new"] == 2


def test_dry_run_writes_no_measurement_files():
    directory = Path(tempfile.mkdtemp()) / "benchmarks"
    store = Store(directory=directory, dry_run=True)
    store.upsert([_record()])
    assert store.save() == []
    assert not directory.exists() or not list(directory.glob("*.json"))


# --- the registries --------------------------------------------------


def test_effort_suffixes_are_conditions_not_models():
    """The single most load-bearing thing the model registry does."""
    registry = load_registry()
    for spelling in ("gpt-6-astra_high", "gpt-6-astra_max", "GPT-6 Astra (low)", "GPT-6 Astra"):
        model = registry.resolve_model(spelling)
        assert model is not None, spelling
        assert model.id == "gpt-6-astra", (spelling, model.id)

    assert effort_of("gpt-6-astra_xhigh") == "xhigh"
    assert effort_of("GPT-6 Astra (low)") == "low"
    assert effort_of("GPT-6 Astra") is None


def test_normalisation_never_drops_a_version_number():
    """It may remove case, punctuation and an effort suffix. A version
    number is identity and must survive."""
    assert normalise("GPT-5.1") != normalise("GPT-5.2")
    assert normalise("Claude Opus 4.5") != normalise("Claude Opus 4.6")
    assert normalise("GPT-5.1 (high)") == normalise("gpt-5.1")


def test_an_unknown_model_does_not_resolve_to_something_close():
    registry = load_registry()
    assert registry.resolve_model("Definitely-Not-A-Real-Model-9000") is None
    # A near-miss must not be coerced onto a real entry.
    assert registry.resolve_model("GPT-99 Nonexistent") is None


def test_benchmark_vocabulary_is_closed():
    registry = load_registry()
    assert registry.resolve_benchmark("gpqa-diamond") is not None
    assert registry.resolve_benchmark("arc-agi-3") is None, (
        "ARC-AGI-3 appears in the archive and is deliberately not tracked"
    )
    assert len(registry.benchmark_slugs()) == 12


# --- the Epoch adapter ----------------------------------------------


def _bundle() -> Path | None:
    return epoch.CACHE_FILE if epoch.CACHE_FILE.exists() else None


def test_epoch_rows_carry_conditions_and_an_attribution():
    bundle = _bundle()
    if bundle is None:
        return  # nothing cached; nothing to assert offline
    registry = load_registry()
    rows, _ = epoch.collect(registry, bundle_path=bundle)
    assert rows
    for row in rows[:200]:
        conditions = row["conditions"]
        assert any(
            conditions.get(key) is not None for key in ("shots", "tools", "reasoningEffort")
        ) or conditions.get("notes"), row["id"]
        assert row["attribution"].startswith("Epoch AI"), row["id"]
        assert "CC-BY" in row["license"]
        assert row["measuredBy"] in ("vendor", "thirdparty", "community")


def test_epoch_respects_the_backfill_cutoff():
    """§14.3, default applied: 2025-01-01 onward, and the cutoff is a
    named constant rather than a number buried in a loop."""
    from core.constants import EPOCH_BACKFILL_START

    assert EPOCH_BACKFILL_START == "2025-01-01"
    bundle = _bundle()
    if bundle is None:
        return
    registry = load_registry()
    rows, _ = epoch.collect(registry, bundle_path=bundle)
    assert all(row["measuredAt"] >= EPOCH_BACKFILL_START for row in rows)
    # ...and widening it is one edit, not a rewrite.
    wider, _ = epoch.collect(registry, bundle_path=bundle, since="2023-01-01")
    assert len(wider) > len(rows)


def test_epoch_internal_runs_and_redistributed_ones_are_told_apart():
    bundle = _bundle()
    if bundle is None:
        return
    registry = load_registry()
    rows, _ = epoch.collect(registry, bundle_path=bundle)
    internal = [r for r in rows if r["evaluator"] == "Epoch AI"]
    external = [r for r in rows if r["evaluator"] != "Epoch AI"]
    assert internal and external
    assert all(r["measuredBy"] == "thirdparty" for r in internal)
    assert all(r["harness"] == "inspect" for r in internal)
    # Epoch redistributes a handful of numbers that came from a vendor's
    # own announcement; those are vendor claims, whatever file they
    # arrive in.
    assert any(r["measuredBy"] == "vendor" for r in external)


def test_a_broken_adapter_does_not_take_the_run_down():
    """§7.1: one broken scraper must never stop the Epoch pull landing."""
    from channels import benchmarks as channel
    from core.constants import ADAPTER_FAILURES_FILE
    from run import Context
    from core.llm import LLM, OFFLINE
    from test_ledger import _FakeLedger

    def exploding(registry, ctx):
        raise RuntimeError("the leaderboard changed its HTML again")

    size_before = (
        ADAPTER_FAILURES_FILE.stat().st_size if ADAPTER_FAILURES_FILE.exists() else 0
    )
    original = channel.ADAPTERS
    channel.ADAPTERS = {
        "broken": exploding,
        "fine": lambda registry, ctx: ([_record()], []),
    }
    try:
        from core.ledger import Queue
        from core.radar import Radar

        ledger = _FakeLedger([], dry_run=True)
        ctx = Context(channel="benchmarks", dry_run=True, llm=LLM(OFFLINE),
                      ledger=ledger, queue=Queue(ledger),
                      radar=Radar(dry_run=True))
        measurements, unresolved, failed = channel.collect(ctx)
    finally:
        channel.ADAPTERS = original

    assert failed == ["broken"]
    assert len(measurements) == 1, "the working adapter still landed"
    tail = ADAPTER_FAILURES_FILE.read_bytes()[size_before:].decode("utf-8")
    assert "the leaderboard changed its HTML again" in tail


# --- what actually got committed ------------------------------------


def test_the_committed_collection_is_internally_consistent():
    if not COLLECTION.exists():
        return
    registry = load_registry()
    files = list(COLLECTION.glob("*.json"))
    assert files, "the collection should not be empty after Phase 4"
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        assert registry.resolve_model(record["model"]) is not None, path.name
        assert registry.resolve_benchmark(record["benchmark"]) is not None, path.name
        assert record["measuredBy"] in ("vendor", "thirdparty", "community"), path.name
        assert record["conditions"], path.name
        # The filename IS the id.
        assert measurement_id(record) == path.stem, path.name


def test_the_collection_shows_a_vendor_claim_next_to_an_independent_run():
    """The contrast is the product (§4.2). If this ever fails, the page
    has become a leaderboard mirror rather than a tracker."""
    if not COLLECTION.exists():
        return
    records = [json.loads(p.read_text(encoding="utf-8")) for p in COLLECTION.glob("*.json")]
    vendor = {(r["benchmark"], r["model"]) for r in records if r["measuredBy"] == "vendor"}
    third = {(r["benchmark"], r["model"]) for r in records if r["measuredBy"] == "thirdparty"}
    assert vendor, "no vendor claims were backfilled"
    assert vendor & third, "no model has both a vendor claim and an independent run"
