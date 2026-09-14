#!/usr/bin/env python3
"""
One-time (re-runnable) seeder for /models.json, the canonical model
registry.

This is deliberately NOT part of any pipeline run. §4.1 of the channels
brief is emphatic that an unresolved model name must never create a
registry entry automatically — silent auto-registration is how a
benchmark tracker ends up with three rows for one model. The runtime
code (scripts/core/registry.py) therefore only ever *reads* this file
and parks what it cannot resolve in state/unresolved_models.jsonl.

Authoring the registry from a curated third-party catalogue is a
different act: a human runs this, reads the diff, and commits it. The
catalogue used is Epoch AI's `model_metadata.csv`, shipped inside their
CC-BY benchmark data bundle — it already carries canonical model
versions, a model *group* (the thing we call a model), display names
and organisations, which is most of the registry's work done by people
who do it full time.

    python3 scripts/seed_models_registry.py [--zip <path>] [--all]

By default only models that carry at least one measurement on a tracked
benchmark (benchmarks.json) at or after EPOCH_BACKFILL_START are
emitted, which keeps the registry to the few hundred models this site
can actually say something about. `--all` emits every model in the
catalogue instead.

Entries already present in models.json are preserved as-is: hand-added
aliases and corrections survive a re-run. New models are appended, and
the file is rewritten sorted by vendor then id.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.constants import (  # noqa: E402
    EPOCH_BACKFILL_START,
    EPOCH_BULK_ZIP_URL,
)
from core.adapters.epoch import (  # noqa: E402
    EPOCH_FILE_TO_SLUG,
    best_date,
    download_bundle,
)

MODELS_FILE = REPO_ROOT / "models.json"

# Epoch's `organization` strings -> the vendor slugs used by
# feeds-releases.json and config/releases.json. Anything not listed
# falls back to a slug of the organisation name, which is stable enough
# to be corrected by hand later.
VENDOR_BY_ORG = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "google deepmind": "google",
    "deepmind": "google",
    "meta ai": "meta",
    "meta": "meta",
    "microsoft": "microsoft",
    "microsoft research": "microsoft",
    "mistral ai": "mistral",
    "nvidia": "nvidia",
    "xai": "xai",
    "alibaba": "alibaba",
    "deepseek": "deepseek",
    "moonshot": "moonshot",
    "moonshot ai": "moonshot",
    "z.ai (zhipu ai)": "zhipu",
    "zhipu ai": "zhipu",
    "minimax": "minimax",
    "bytedance": "bytedance",
    "tencent": "tencent",
    "baidu": "baidu",
    "ibm": "ibm",
    "cohere": "cohere",
    "reka ai": "reka",
    "reka": "reka",
    "liquid ai": "liquid",
    "allen institute for ai": "ai2",
    "amazon": "amazon",
    "databricks": "databricks",
    "01.ai": "01ai",
    "thinking machines": "thinkingmachines",
    "nous research": "nous",
    "eleutherai": "eleutherai",
}

# Version tokens, removed anywhere in the name to get the family:
# "Claude Opus 4.8" -> "claude-opus", "Gemini 3.7 Flash" ->
# "gemini-flash", "DeepSeek-V3.2" -> "deepseek". A token that mixes
# letters and digits ("R1", "o3", "4o") is kept, because there the digit
# is part of the family's name rather than its version.
VERSION_TOKEN = re.compile(r"(?<![a-z0-9])v?\d+(?:\.\d+)*(?![a-z0-9])", re.I)

# Reasoning-effort / thinking-budget suffixes Epoch appends to a model
# version. These are *conditions*, not different models — collapsing
# them is the single most load-bearing thing this registry does.
EFFORT_SUFFIX = re.compile(
    r"_(none|minimal|low|medium|high|xhigh|max|ultra|unknown|think|"
    r"nothink|thinking|reasoning)$",
    re.I,
)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def vendor_slug(organization: str) -> str:
    """First named organisation wins — Epoch comma-joins collaborators
    ("NVIDIA,Meta AI") and the first is the one that shipped it."""
    first = (organization or "").split(",")[0].strip()
    if not first:
        return "unknown"
    return VENDOR_BY_ORG.get(first.lower(), slugify(first))


def family_of(group: str) -> str:
    """Best-effort family id: the model group with its version numbers
    removed. Deliberately conservative — a wrong family only costs a
    slightly noisier entity-dedup key, whereas a wrong canonical id
    costs a duplicate row in the tracker."""
    stripped = VERSION_TOKEN.sub(" ", group)
    return slugify(stripped) or slugify(group)


def strip_effort(model_version: str) -> str:
    return EFFORT_SUFFIX.sub("", model_version)


def open_weights(accessibility: str) -> bool:
    return "open weights" in (accessibility or "").lower()


def tracked_model_versions(bundle: zipfile.ZipFile) -> set[str]:
    """Model versions with at least one measurement on a tracked
    benchmark inside the backfill window."""
    keep: set[str] = set()
    for filename in EPOCH_FILE_TO_SLUG:
        if filename not in bundle.namelist():
            continue
        rows = csv.DictReader(io.StringIO(bundle.read(filename).decode("utf-8")))
        for row in rows:
            version = (row.get("Model version") or "").strip()
            if not version:
                continue
            measured_at = best_date(row)
            if not measured_at or measured_at < EPOCH_BACKFILL_START:
                continue
            keep.add(version)
    return keep


def build(bundle: zipfile.ZipFile, everything: bool) -> list[dict]:
    catalogue = [
        row
        for row in csv.DictReader(
            io.StringIO(bundle.read("model_metadata.csv").decode("utf-8"))
        )
        if (row.get("model_version") or "").strip()
    ]
    wanted = None if everything else tracked_model_versions(bundle)

    by_id: dict[str, dict] = {}
    for row in catalogue:
        version = row["model_version"].strip()
        if wanted is not None and version not in wanted:
            continue
        group = (row.get("model_group") or "").strip() or version
        model_id = slugify(group)
        if not model_id:
            continue

        entry = by_id.setdefault(
            model_id,
            {
                "id": model_id,
                "vendor": vendor_slug(row.get("organization", "")),
                "family": family_of(group),
                # The *group* name, never a display name — Epoch's
                # display names carry the reasoning-effort variant
                # ("GPT-6 Astra (high)"), and effort is a condition on a
                # measurement, not part of the model's name.
                "displayName": group,
                "aliases": set(),
                "releasedAt": (row.get("date") or "").strip() or None,
                "openWeights": open_weights(row.get("accessibility", "")),
            },
        )
        # Every spelling this model turns up under becomes an alias:
        # the raw Epoch version string, the same string with its
        # reasoning-effort suffix removed, the display name, and the
        # group name itself.
        entry["aliases"].update(
            {
                version,
                strip_effort(version),
                group,
                (row.get("display_name") or "").strip(),
            }
        )
        entry["aliases"].discard("")
        # Earliest date wins: a model is released once, even though
        # every effort variant carries the same date here.
        date = (row.get("date") or "").strip()
        if date and (not entry["releasedAt"] or date < entry["releasedAt"]):
            entry["releasedAt"] = date
        entry["openWeights"] = entry["openWeights"] or open_weights(
            row.get("accessibility", "")
        )

    out = []
    for entry in by_id.values():
        aliases = sorted(a for a in entry["aliases"] if slugify(a) != entry["id"])
        record = {
            "id": entry["id"],
            "vendor": entry["vendor"],
            "family": entry["family"],
            "displayName": entry["displayName"],
            "aliases": aliases,
            "openWeights": entry["openWeights"],
        }
        if entry["releasedAt"]:
            record["releasedAt"] = entry["releasedAt"]
        out.append(record)
    return out


def merge(existing: list[dict], seeded: list[dict]) -> tuple[list[dict], int]:
    """Existing entries win on every field — a hand correction must
    survive a re-seed — but pick up any aliases the catalogue has
    learned since."""
    by_id = {e["id"]: e for e in existing}
    added = 0
    for entry in seeded:
        current = by_id.get(entry["id"])
        if current is None:
            by_id[entry["id"]] = entry
            added += 1
            continue
        merged_aliases = sorted(set(current.get("aliases", [])) | set(entry["aliases"]))
        current["aliases"] = merged_aliases
    ordered = sorted(by_id.values(), key=lambda e: (e["vendor"], e["id"]))
    return ordered, added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None, help="local benchmark_data.zip")
    parser.add_argument("--all", action="store_true", help="seed every catalogued model")
    args = parser.parse_args()

    path = args.zip or download_bundle()
    print(f"Reading catalogue from {path}", file=sys.stderr)
    with zipfile.ZipFile(path) as bundle:
        seeded = build(bundle, args.all)

    document = {}
    existing: list[dict] = []
    if MODELS_FILE.exists():
        document = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
        existing = document.get("models", [])

    models, added = merge(existing, seeded)
    document["_comment"] = (
        "Canonical model registry — a CLOSED vocabulary. Resolution order is "
        "exact id, then exact alias, then normalised (lowercase, strip "
        "spaces/dashes/parentheses/reasoning-effort suffix), then UNRESOLVED. "
        "An unresolved name is parked in state/unresolved_models.jsonl and "
        "reported weekly; it is never auto-registered and never written into "
        "the benchmarks collection. Seeded from Epoch AI's CC-BY model "
        "catalogue by scripts/seed_models_registry.py, which is run by hand "
        "and never by the pipeline. Hand edits to an existing entry survive a "
        "re-seed; only aliases are merged in."
    )
    document["source"] = EPOCH_BULK_ZIP_URL
    document["models"] = models
    MODELS_FILE.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"{len(models)} models in {MODELS_FILE.name} ({added} new this run).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
