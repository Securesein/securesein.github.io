"""
The verification gates (brief §9) — what replaces human review.

Run in order; any failure means no publication, and every failure is
written to state/rejected.jsonl with the gate id and the offending
content. There is no retry with a different prompt and no override:
a draft that fails a gate is rejected and logged, full stop.

  G1  numeric grounding      deterministic. Every number in the draft
                             must appear in the fetched source.
  G2  entity grounding       deterministic. The family and version must
                             appear in the source; every model named in
                             a roundup must resolve in models.json.
  G3  verifier model         a cheap model, a fixed checklist, strict
                             JSON. Any false, any invented claim, or
                             unparseable output -> reject.
  G4  schema validation      already exists: `astro build` in CI.
  G5  reference integrity    every benchmarkRefs id resolves, and every
                             number in a roundup traces to one of those
                             measurements.

G1 is the cheap one and the important one. It is the primary defence
against an invented benchmark score, it costs nothing, and it cannot be
talked out of a rejection — which is exactly what a reviewless pipeline
needs and what a model-based check cannot promise.

A note on G1's matching. The brief says "regex and string matching, no
model judgement", and lists the normalisations that matter: thousands
separators, %, $, unit spacing, 1.5k <-> 1500. String matching alone
cannot do the last of those, so numbers are parsed to a canonical
value and compared numerically. That is still fully deterministic and
still has no model in it; it is simply a better way to say "1.05M and
1,050,000 are the same number".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import llm as llm_module
from .registry import Registry

# --- shared number handling -----------------------------------------

MAGNITUDES = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "mn": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "t": 1_000_000_000_000.0,
    "thousand": 1_000.0,
    "million": 1_000_000.0,
    "billion": 1_000_000_000.0,
    "trillion": 1_000_000_000_000.0,
}

# A number, with optional thousands separators, optional decimals, an
# optional magnitude word or letter, and an optional percent sign.
NUMBER = re.compile(
    r"(?<![\w.])"
    r"(\d{1,3}(?:,\d{3})+|\d+)"          # 1,050,000 or 1050000 or 98
    r"(?:\.(\d+))?"                       # .05
    r"\s*"
    r"(k|m|mn|b|bn|t|thousand|million|billion|trillion)?"
    r"\s*"
    r"(%)?"
    # A following "." is fine as long as it is not the start of another
    # number component. The original lookahead was `(?![\w.])`, which
    # meant a SENTENCE-FINAL figure was never extracted at all: "up from
    # 61.5% for Aurora 2.0." put no 2.0 in the source set, so a draft
    # that said "Aurora 2.0," with a comma was rejected by G1 for
    # stating a number the source plainly contained. Found by
    # scripts/tests/test_publication_paths.py, which reproduced it on a
    # draft that differed from an honest one by nothing at all.
    r"(?!\w|\.\d)",
    re.I,
)

# Numbers that are part of how a thing is spelled rather than a claim
# about the world. A version string is checked by G2 against the source
# directly, so letting G1 see "4.5" inside "Claude Opus 4.5" as a bare
# number would reject every correct draft.
VERSIONISH = re.compile(r"[A-Za-z][\w.\-]*?\d[\w.\-]*")


def _canonical(match: re.Match) -> float | None:
    whole, decimals, magnitude, percent = match.groups()
    try:
        value = float(whole.replace(",", "") + ("." + decimals if decimals else ""))
    except ValueError:
        return None
    if magnitude:
        value *= MAGNITUDES[magnitude.lower()]
    if percent:
        # Recorded as the percentage, not the fraction; the source-side
        # set carries both forms so 98% still matches "0.98".
        return value
    return value


def numbers_in(text: str, *, drop_versionish: bool = False) -> set[float]:
    """Every number in a piece of text, canonicalised."""
    working = text or ""
    if drop_versionish:
        # Blank out tokens like "GPT-4.1" and "v2.5" so their digits are
        # not read as free-standing figures.
        working = VERSIONISH.sub(" ", working)
    found: set[float] = set()
    for match in NUMBER.finditer(working):
        value = _canonical(match)
        if value is None:
            continue
        found.add(round(value, 6))
        if match.group(4):  # a percentage also matches its fraction
            found.add(round(value / 100, 6))
        else:
            found.add(round(value * 100, 6))
    return found


@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str = ""
    offending: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed


# --- G1 ---------------------------------------------------------------


def g1_numeric_grounding(draft_body: str, source_text: str) -> GateResult:
    """Every number in the draft must appear in the source.

    Deterministic, cheap, and unarguable. This is the gate that stops a
    model rounding 97.6 to 98, or inventing a context window it half
    remembers from a different model.
    """
    in_source = numbers_in(source_text)
    ungrounded = []
    # Versionish tokens are dropped on the DRAFT side only: "Claude Opus
    # 4.5" is an entity, and G2 checks entities against the source.
    for match in NUMBER.finditer(VERSIONISH.sub(" ", draft_body or "")):
        value = _canonical(match)
        if value is None:
            continue
        candidates = {round(value, 6), round(value / 100, 6), round(value * 100, 6)}
        if not (candidates & in_source):
            ungrounded.append(match.group(0).strip())

    if ungrounded:
        return GateResult(
            "G1",
            False,
            f"{len(ungrounded)} number(s) in the draft do not appear in the source",
            sorted(set(ungrounded)),
        )
    return GateResult("G1", True, "every number in the draft is present in the source")


# --- G2 ---------------------------------------------------------------


def _mentions(needle: str, haystack: str) -> bool:
    """Punctuation- and case-insensitive containment, for NAMES."""
    if not needle:
        return False
    squashed = re.sub(r"[^a-z0-9]+", "", needle.lower())
    return squashed in re.sub(r"[^a-z0-9]+", "", haystack.lower())


def _mentions_version(version: str, haystack: str) -> bool:
    """Containment for a VERSION, which is a different problem.

    Squashing punctuation out of "6" and looking for it in a source that
    says "47% less time" finds a 7 and a 4 and declares victory, so a
    wrong version would sail through G2 — which was exactly the bug this
    function exists to fix. A version has to appear with digit
    boundaries on both sides.
    """
    if not version:
        return False
    pattern = re.compile(rf"(?<![\d.]){re.escape(version)}(?![\d.%])", re.I)
    return bool(pattern.search(haystack or ""))


def g2_entity_grounding(
    release: dict, source_text: str, registry: Registry
) -> GateResult:
    """The family and the version must actually be in the source.

    A release post whose subject the source never names is not a report
    of a release; it is a model writing about what it expected to find.
    """
    missing = []

    family = release.get("family", "")
    model = registry.resolve_model(release.get("modelHint") or family)
    spellings = [family.replace("-", " "), family]
    if model:
        spellings.extend([model.display_name, *model.aliases])
    if not any(_mentions(name, source_text) for name in spellings if name):
        missing.append(f"family {family!r}")

    version = release.get("version", "")
    if version and not _mentions_version(version, source_text):
        missing.append(f"version {version!r}")

    if missing:
        return GateResult(
            "G2", False, "the source does not name what this post is about", missing
        )
    return GateResult("G2", True, "family and version both appear in the source")


def g2_models_resolve(names: list[str], registry: Registry) -> GateResult:
    """The roundup half of G2: every model a roundup names must be a
    canonical id, not a plausible-looking string."""
    unresolved = [n for n in names if registry.resolve_model(n) is None]
    if unresolved:
        return GateResult(
            "G2", False, "a roundup named a model that is not in the registry", unresolved
        )
    return GateResult("G2", True, f"{len(names)} model name(s) all resolve")


# --- G3 ---------------------------------------------------------------

G3_PROMPT = """You are checking a short draft against the source it was
written from. You are not editing it and not improving it — you are
answering four questions about it.

SOURCE:
{source}

DRAFT:
{draft}

Answer:
- every_claim_in_source: is every factual claim in the draft supported
  by the source text above?
- invented_claims: list any claim in the draft that the source does not
  support. Empty list if there are none.
- version_matches_source: does the draft name the same model version
  the source does?
- vendor_claims_attributed: is every performance or benchmark claim in
  the draft explicitly attributed to the vendor, rather than stated as
  established fact?

Return ONLY JSON:
{{"every_claim_in_source": true|false, "invented_claims": [],
  "version_matches_source": true|false,
  "vendor_claims_attributed": true|false, "verdict": "pass"|"fail"}}"""


def g3_verifier(llm, draft_body: str, source_text: str) -> GateResult:
    """A cheap model, a fixed checklist, strict JSON.

    Any false, any non-empty invented_claims, or unparseable JSON is a
    rejection. The brief is explicit that there is no retry with a
    different prompt, because a gate you can re-roll is not a gate.

    With --offline-llm there is no verifier, so this FAILS CLOSED and
    nothing publishes. That is the correct asymmetry: the other gates
    fail open in specific documented places because a missed post costs
    less than a stalled pipeline, but the gate whose whole job is to
    catch invented claims must never wave a draft through because it
    could not run.
    """
    verdict = llm.json(
        G3_PROMPT.format(source=source_text[:6000], draft=draft_body),
        model=llm_module.VERIFY_MODEL,
        temperature=0,
        label="G3 verifier",
    )
    if not isinstance(verdict, dict):
        return GateResult(
            "G3", False, "the verifier produced no usable JSON (or was unavailable)"
        )

    invented = verdict.get("invented_claims") or []
    checks = {
        "every_claim_in_source": verdict.get("every_claim_in_source"),
        "version_matches_source": verdict.get("version_matches_source"),
        "vendor_claims_attributed": verdict.get("vendor_claims_attributed"),
    }
    failed = [name for name, value in checks.items() if value is not True]
    if failed or invented or verdict.get("verdict") != "pass":
        return GateResult(
            "G3",
            False,
            f"verifier rejected: {', '.join(failed) or verdict.get('verdict', 'no verdict')}",
            list(invented),
        )
    return GateResult("G3", True, "verifier passed all four checks")


# --- G5 ---------------------------------------------------------------


def g5_reference_integrity(
    draft_body: str, benchmark_refs: list[str], known_ids: set[str], values: dict
) -> GateResult:
    """Every cited id exists, and every number in the draft traces to
    one of the cited measurements.

    The second half is what makes a roundup honest: a post may only
    state numbers that are in the collection, so there is no path by
    which a figure reaches a reader without also being a record someone
    can check.
    """
    dangling = [ref for ref in benchmark_refs if ref not in known_ids]
    if dangling:
        return GateResult(
            "G5", False, "benchmarkRefs cites measurements that do not exist", dangling
        )
    if not benchmark_refs:
        return GateResult("G5", False, "a roundup must cite at least one measurement")

    cited = set()
    for ref in benchmark_refs:
        value = values.get(ref)
        if value is None:
            continue
        cited.update({round(float(value), 6), round(float(value) / 100, 6),
                      round(float(value) * 100, 6)})

    untraceable = []
    for match in NUMBER.finditer(VERSIONISH.sub(" ", draft_body or "")):
        if not _is_figure(match):
            continue
        value = _canonical(match)
        if value is None:
            continue
        candidates = {round(value, 6), round(value / 100, 6), round(value * 100, 6)}
        if not (candidates & cited):
            untraceable.append(match.group(0).strip())

    if untraceable:
        return GateResult(
            "G5",
            False,
            "the draft states numbers that trace to no cited measurement",
            sorted(set(untraceable)),
        )
    return GateResult("G5", True, f"{len(benchmark_refs)} reference(s), all traced")


def _is_figure(match: re.Match) -> bool:
    """Whether a number in a roundup is a SCORE rather than an ordinary
    small integer.

    G1 can afford to be absolute — every number in a release draft must
    be in the source, and "Tier 4" is in the source too. G5 compares
    against the values of the cited measurements only, so a bare "4" in
    "FrontierMath Tier 4", or "five" written as "5", legitimately traces
    to nothing and must not be read as an untraceable score. A figure
    carries a percent sign, a decimal point, or four or more digits.
    """
    whole, decimals, magnitude, percent = match.groups()
    return bool(percent or decimals or magnitude or len(whole.replace(",", "")) >= 4)


# --- the sequence -----------------------------------------------------


def run_release_gates(llm, draft: dict, release: dict, source_text: str, registry) -> list[GateResult]:
    """G1 -> G2 -> G3, stopping at the first failure. Order is cost
    order: the free deterministic checks run before the paid one."""
    results = [g1_numeric_grounding(draft["body"], source_text)]
    if not results[-1]:
        return results
    results.append(g2_entity_grounding(release, source_text, registry))
    if not results[-1]:
        return results
    results.append(g3_verifier(llm, draft["body"], source_text))
    return results
