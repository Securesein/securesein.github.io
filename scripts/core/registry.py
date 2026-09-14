"""
Closed-vocabulary resolution for models and benchmarks.

Two registries, both at the repo root next to taxonomy.json so the
Astro site and this pipeline read the identical bytes:

  models.json      canonical model ids + aliases
  benchmarks.json  tracked benchmarks

The single rule that makes this channel worth having: **an unresolved
name is never invented into existence.** No auto-registration, no
"close enough" fuzzy match onto an existing id, no writing an
unresolved model into the collection. Unresolved names are parked in
state/unresolved_models.jsonl and surface in the weekly report, where a
human decides whether they are a genuinely new model (add it to
models.json) or noise (ignore it).

Resolution order for a model name, per brief §4.1:
  1. exact id
  2. exact alias
  3. normalised (lowercase; strip spaces, dashes, underscores, dots,
     parentheses, and any trailing reasoning-effort suffix)
  4. UNRESOLVED
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from .constants import BENCHMARKS_REGISTRY_FILE, MODELS_REGISTRY_FILE

# Reasoning effort / thinking budget is a *condition*, not a different
# model. "gpt-6-astra_high" and "GPT-6 Astra (high)" are the same model
# run two ways, and collapsing them is the difference between a tracker
# with one row per model and one with seven.
EFFORT_TOKENS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
    "unknown",
    "unknown thinking",
    "think",
    "nothink",
    "thinking",
    "non-thinking",
    "reasoning",
    "default",
)
_EFFORT_SUFFIX = re.compile(
    r"[\s_\-]*[\(\[]?(" + "|".join(re.escape(t) for t in EFFORT_TOKENS) + r")[\)\]]?$",
    re.I,
)
_PAREN = re.compile(r"\(([^)]*)\)")


@dataclass(frozen=True)
class Model:
    id: str
    vendor: str
    family: str
    display_name: str
    aliases: tuple[str, ...]
    open_weights: bool
    released_at: str | None


@dataclass(frozen=True)
class Benchmark:
    slug: str
    name: str
    description: str
    metric: str
    unit: str
    higher_is_better: bool
    homepage: str


def normalise(name: str) -> str:
    """Aggressive but *lossless-in-identity* normalisation: it may only
    ever remove punctuation, case and effort suffixes. It must never
    drop a version number, because a version number is identity."""
    stripped = _EFFORT_SUFFIX.sub("", (name or "").strip())
    return re.sub(r"[^a-z0-9]+", "", stripped.lower())


def effort_of(name: str) -> str | None:
    """The reasoning-effort condition encoded in a model name, if any —
    "gpt-6-astra_xhigh" -> "xhigh", "GPT-5.1 (high)" -> "high"."""
    candidate = (name or "").strip()
    inner = _PAREN.search(candidate)
    if inner and inner.group(1).strip().lower() in EFFORT_TOKENS:
        return inner.group(1).strip().lower()
    tail = candidate.rsplit("_", 1)[-1].strip().lower() if "_" in candidate else ""
    if tail in EFFORT_TOKENS:
        return tail
    return None


class Registry:
    """Loaded once per run; both files are small and read-only here."""

    def __init__(self, models: Iterable[Model], benchmarks: Iterable[Benchmark]):
        self.models = {m.id: m for m in models}
        self.benchmarks = {b.slug: b for b in benchmarks}

        self._by_alias: dict[str, str] = {}
        self._by_normal: dict[str, str] = {}
        for model in self.models.values():
            for name in (model.id, model.display_name, *model.aliases):
                if not name:
                    continue
                self._by_alias.setdefault(name, model.id)
                # First writer wins, so an ambiguous normalised form
                # resolves deterministically rather than by dict order.
                self._by_normal.setdefault(normalise(name), model.id)

    # -- models ------------------------------------------------------

    def resolve_model(self, name: str) -> Model | None:
        if not name:
            return None
        raw = name.strip()
        if raw in self.models:
            return self.models[raw]
        alias = self._by_alias.get(raw)
        if alias:
            return self.models[alias]
        normal = self._by_normal.get(normalise(raw))
        if normal:
            return self.models[normal]
        return None

    def models_of_vendor(self, vendor: str) -> list[Model]:
        return [m for m in self.models.values() if m.vendor == vendor]

    # -- benchmarks --------------------------------------------------

    def resolve_benchmark(self, slug: str) -> Benchmark | None:
        return self.benchmarks.get((slug or "").strip())

    def benchmark_slugs(self) -> list[str]:
        return list(self.benchmarks)


def _load_models() -> list[Model]:
    document = json.loads(MODELS_REGISTRY_FILE.read_text(encoding="utf-8"))
    return [
        Model(
            id=entry["id"],
            vendor=entry.get("vendor", "unknown"),
            family=entry.get("family", entry["id"]),
            display_name=entry.get("displayName", entry["id"]),
            aliases=tuple(entry.get("aliases", [])),
            open_weights=bool(entry.get("openWeights", False)),
            released_at=entry.get("releasedAt"),
        )
        for entry in document.get("models", [])
    ]


def _load_benchmarks() -> list[Benchmark]:
    document = json.loads(BENCHMARKS_REGISTRY_FILE.read_text(encoding="utf-8"))
    return [
        Benchmark(
            slug=entry["slug"],
            name=entry["name"],
            description=entry.get("description", ""),
            metric=entry.get("metric", "accuracy"),
            unit=entry.get("unit", "percent"),
            higher_is_better=bool(entry.get("higherIsBetter", True)),
            homepage=entry.get("homepage", ""),
        )
        for entry in document.get("benchmarks", [])
    ]


@lru_cache(maxsize=1)
def load_registry() -> Registry:
    return Registry(_load_models(), _load_benchmarks())
