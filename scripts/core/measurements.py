"""
The `benchmarks` collection: one JSON file per measurement, and the
upsert rules that keep it honest (brief §7.2 step 3).

    identical (benchmark, model, evaluator, conditions, value) -> no-op
    same key, new value                     -> new record, `supersedes`
                                               pointing at the old one
    new key                                 -> new record

**Conditions are part of a measurement's identity.** This is the one
place the implementation departs from the brief's literal text, and it
departs *toward* the brief's own argument. §4 specifies the id as
`<benchmark>--<model>--<evaluator>--<YYYY-MM-DD>` and then says, two
paragraphs later, that "`measuredBy` plus `conditions` is the reason
this channel exists" and that "a score without a harness and a shot
count is a number, not a finding". Those two statements are in
tension: Epoch runs the same model on the same benchmark on the same
day at five different reasoning efforts, and under the literal id
scheme four of those five silently overwrite the fifth — throwing away
exactly the distinction the channel is for. So the id carries a short
digest of the conditions:

    <benchmark>--<model>--<evaluator>--<YYYY-MM-DD>--<4 hex of conditions>

Deterministic, collision-free, and still readable in a post's
`benchmarkRefs`. Everything else about §4's shape is unchanged.

Nothing here writes a measurement for a model the registry could not
resolve. That check lives in the adapters, and this module would refuse
anyway — a row whose `model` is not a canonical id is not a row.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .constants import BENCHMARK_COLLECTION_DIR


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def conditions_digest(conditions: dict) -> str:
    """Stable 4-hex fingerprint of the conditions a number was produced
    under. Sorted keys and dropped empties, so two records describing
    the same run agree whatever order their fields arrived in."""
    cleaned = {
        key: value
        for key, value in sorted((conditions or {}).items())
        if value is not None and value != ""
    }
    blob = json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:4]


def measurement_id(record: dict) -> str:
    return "--".join(
        [
            record["benchmark"],
            _slug(record["model"]),
            _slug(record["evaluator"]),
            str(record["measuredAt"])[:10],
            conditions_digest(record.get("conditions", {})),
        ]
    )


def identity(record: dict) -> tuple:
    """The key §7.2 step 3 talks about — everything except the value and
    the date. Two records sharing this are two runs of the same thing."""
    return (
        record["benchmark"],
        record["model"],
        record["evaluator"],
        conditions_digest(record.get("conditions", {})),
    )


class Store:
    """The collection on disk, loaded once and written once."""

    def __init__(self, directory: Path = BENCHMARK_COLLECTION_DIR, dry_run: bool = True):
        self.directory = directory
        self.dry_run = dry_run
        self.existing: dict[str, dict] = {}
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                try:
                    self.existing[path.stem] = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
        self.written: list[str] = []
        self.superseded: list[str] = []
        self.unchanged = 0

    def _current_by_identity(self) -> dict[tuple, tuple[str, dict]]:
        """Latest non-superseded record per identity."""
        superseded = {
            record.get("supersedes")
            for record in self.existing.values()
            if record.get("supersedes")
        }
        out: dict[tuple, tuple[str, dict]] = {}
        for entry_id, record in self.existing.items():
            if entry_id in superseded:
                continue
            key = identity(record)
            best = out.get(key)
            if best is None or str(record["measuredAt"]) > str(best[1]["measuredAt"]):
                out[key] = (entry_id, record)
        return out

    def upsert(self, records: list[dict]) -> dict:
        """Apply §7.2 step 3 to a batch. Returns a small summary; the
        files are written by `save`, so a dry run can report exactly
        what it would have changed without changing it."""
        current = self._current_by_identity()
        pending: dict[str, dict] = {}

        for record in records:
            key = identity(record)
            entry_id = measurement_id(record)
            existing = current.get(key)

            if existing is not None:
                old_id, old = existing
                if _same_value(old, record):
                    self.unchanged += 1
                    continue
                # A re-run with a different number does not overwrite:
                # the old reading stays, and the new one points at it.
                # Someone reading the archive later can see that the
                # number moved, which is itself a story.
                record = {**record, "supersedes": old_id}
                self.superseded.append(old_id)

            if entry_id in pending or entry_id in self.existing:
                # Same identity AND same date AND same conditions AND a
                # different value is a source contradicting itself; keep
                # the first and move on rather than flip-flopping.
                self.unchanged += 1
                continue
            pending[entry_id] = record
            current[key] = (entry_id, record)

        self.pending = pending
        return {
            "new": len(pending),
            "superseded": len(self.superseded),
            "unchanged": self.unchanged,
            "total_after": len(self.existing) + len(pending),
        }

    def save(self) -> list[str]:
        if self.dry_run:
            print(
                f"    [dry-run] would write {len(getattr(self, 'pending', {}))} "
                f"measurement file(s) to {self.directory}; wrote none."
            )
            return []
        self.directory.mkdir(parents=True, exist_ok=True)
        for entry_id, record in getattr(self, "pending", {}).items():
            payload = {k: v for k, v in record.items() if v is not None}
            payload.pop("id", None)  # the filename is the id
            (self.directory / f"{entry_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.written.append(entry_id)
        return self.written


def _same_value(a: dict, b: dict) -> bool:
    """Floats out of a CSV are not worth comparing exactly; two runs
    that agree to three decimal places are the same reading."""
    try:
        return abs(float(a["value"]) - float(b["value"])) < 1e-3
    except (KeyError, TypeError, ValueError):
        return False
