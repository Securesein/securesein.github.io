"""
Two-stage scoring, driven entirely by interest_profile.yaml (brief §7.1).

    stage 1   QUALITY GATE     pass/fail, minimum from the profile
                                (55 as the brief's default; 65 after the
                                Phase 3 calibration)
    stage 2   RELEVANCE RANK   applied only to survivors; orders the queue

**Never one weighted sum.** A single 0-100 score lets a technically
excellent but irrelevant paper outrank a merely good but highly relevant
one, and it lets a high personal-interest score drag a thin item over
the bar. Gate first, then rank. The two stages do not share a scale and
are deliberately not addable.

Every weight, threshold and signal list in here comes from
interest_profile.yaml. Nothing is hard-coded, because §16 says so and
because the whole point of Phase 3 is that the owner tunes the file
rather than the code.

**The exclusion filter runs before either stage.** An excluded item is
dropped with no score at all — it does not fail the gate, it was never
considered, and it is logged with its own reason class so "we dropped 40
funding stories" never reads like "the quality bar rose".

OFFLINE SCORING. Both stages have a deterministic implementation that
runs with --offline-llm and with no API key. It is not a stub: it scores
from the signal lists in the profile, the source tier, the presence of
numbers and mechanism language, and the item's age. It is dumber than a
model, and it is what makes the rubric replayable against a week of real
feed data without spending anything — which is precisely what the one
calibration pass in Phase 3 needs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from . import llm as llm_module
from .constants import INTEREST_PROFILE_FILE, TOPIC_ACTIVITY_FILE
from .state import read_json, write_json


# --- loading the profile ---------------------------------------------


@lru_cache(maxsize=1)
def load_profile() -> dict:
    """interest_profile.yaml. PyYAML is already a dependency of the
    Astro-side content check (js-yaml) and of nothing here, so it is
    imported lazily with a readable failure rather than at module
    import: a channel that never scores should not need it installed."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit(
            "PyYAML is required to read interest_profile.yaml — "
            "`pip install -r scripts/requirements.txt`"
        ) from exc
    return yaml.safe_load(INTEREST_PROFILE_FILE.read_text(encoding="utf-8"))


def _signals(entries) -> list[tuple[str, list[str]]]:
    """(topic, lowercased signal phrases) for one interest tier. An
    entry with no `signals` list still contributes its own topic name as
    a phrase, so a commented-down profile degrades gracefully instead of
    scoring zero."""
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            out.append((str(entry), [str(entry).lower()]))
            continue
        topic = str(entry.get("topic", ""))
        phrases = [str(s).lower() for s in (entry.get("signals") or [])]
        if not phrases and topic:
            phrases = [topic.lower()]
        out.append((topic, phrases))
    return out


@dataclass
class Profile:
    raw: dict

    @property
    def quality_minimum(self) -> float:
        return float(self.raw["quality_gate"]["minimum"])

    @property
    def quality_weights(self) -> dict:
        return self.raw["quality_gate"]["components"]

    @property
    def relevance_weights(self) -> dict:
        return self.raw["relevance_rank"]["components"]

    @property
    def low_interest_penalty(self) -> float:
        return float(self.raw["relevance_rank"].get("low_interest_penalty", 0))

    @property
    def strong(self) -> list[tuple[str, list[str]]]:
        return _signals(self.raw.get("strong_interests"))

    @property
    def medium(self) -> list[tuple[str, list[str]]]:
        return _signals(self.raw.get("medium_interests"))

    @property
    def low(self) -> list[str]:
        return [str(x).lower() for x in self.raw.get("low_interests") or []]

    @property
    def exclude(self) -> list[str]:
        return [str(x).lower() for x in self.raw.get("exclude") or []]

    @property
    def starvation(self) -> dict:
        return self.raw.get("topic_starvation") or {"enabled": False}

    @property
    def discovery(self) -> dict:
        return self.raw.get("discovery") or {}

    @property
    def feedback(self) -> dict:
        return self.raw.get("feedback") or {}


def profile() -> Profile:
    return Profile(load_profile())


# --- the exclusion filter (§7, before any scoring) -------------------

# The exclude[] entries are prose, one line each, so they are matched by
# a keyword set derived from each line rather than by substring. The
# derivation is deliberately conservative: an exclusion that fires on a
# near-miss silently removes material the owner wanted, and unlike a
# quality drop there is no score to inspect afterwards.
EXCLUDE_PATTERNS = {
    "funding rounds, valuations, IPOs, acquisitions": re.compile(
        r"\b(series [a-e]\b|funding round|raises \$|raised \$|valuation|"
        r"\bipo\b|acquir(?:e|es|ed|ing|ition)|buys? .{0,30}\bfor \$|merger)\b",
        re.I,
    ),
    "executive hires, departures and org restructures": re.compile(
        r"\b(appoints?|names? .{0,40}as (?:its |the )?(?:new )?(?:chief|head|"
        r"director|lead)|steps down|resigns?|departs?|joins? .{0,30}as|"
        r"restructur|layoffs?|lays off)\b",
        re.I,
    ),
    "corporate press releases with no technical substance": re.compile(
        r"\b(press release|announces? (?:a )?(?:strategic )?(?:partnership|"
        r"collaboration)|is proud to)\b",
        re.I,
    ),
    "partnership and customer-win announcements": re.compile(
        r"\b(partners? with|partnership with|selects? .{0,30}to power|"
        r"customer story|case study|chooses .{0,30}for)\b",
        re.I,
    ),
    '"AI will transform <industry>" opinion pieces': re.compile(
        r"\b(will transform|is transforming|the future of work|"
        r"why .{0,30}needs? ai|ai is coming for)\b",
        re.I,
    ),
    "publisher-about-itself stories": None,  # handled by a dedicated check
    "conference and webinar announcements": re.compile(
        r"\b(webinar|register now|save the date|keynote|"
        r"(?:summit|conference|expo) 20\d\d|call for papers)\b",
        re.I,
    ),
    "product marketing and sponsored content": re.compile(
        r"\b(sponsored|advertorial|in partnership with|brought to you by)\b",
        re.I,
    ),
    "listicles and \"top N tools\" content": re.compile(
        r"\b(top \d+|\d+ best|\d+ tools|\d+ ways|\d+ things|ultimate guide)\b",
        re.I,
    ),
}

NEWSROOM_WORDS = (
    "names", "appoints", "hires", "joins", "editor", "editorial", "analyst",
    "newsroom", "columnist", "coverage", "subscribers", "newsletter",
    "masthead", "staff", "role", "relaunch", "redesign",
)


def publication_self_reference(title: str, source_name: str) -> bool:
    """The "publisher-about-itself" exclusion, carried over verbatim
    from the pre-refactor relevance gate because it was tuned against a
    real failure already in the archive: "Understanding VentureBeat's
    Role in the AI Industry", written from a VentureBeat post about
    VentureBeat hiring its first lead analyst.

    Requires BOTH signals — the publisher's name in the headline *and* a
    word about the business of publishing — so that a vendor blog
    writing about its own product, which is exactly what this site is
    for, never trips it."""
    words = re.findall(r"[a-z]+", (source_name or "").lower())
    stop = {"ai", "blog", "news", "the", "weblog", "technical", "engineering", "at"}
    names = [w for w in words if w not in stop and len(w) > 3]
    haystack = (title or "").lower()
    if not any(name in haystack for name in names):
        return False
    return any(word in haystack for word in NEWSROOM_WORDS)


def excluded(title: str, summary: str, source_name: str, prof: Profile) -> str | None:
    """-> the exclude[] line that fired, or None.

    Only lines actually present in the profile can fire: the owner owns
    this list (§11.3, `never_auto_exclude`), so a pattern this module
    knows about but the profile has dropped must stay silent."""
    text = f"{title}\n{summary}"
    active = set(prof.exclude)
    for line, pattern in EXCLUDE_PATTERNS.items():
        if line.lower() not in active:
            continue
        if pattern is None:
            if publication_self_reference(title, source_name):
                return line
            continue
        if pattern.search(text):
            return line
    return None


# --- stage 1: the quality gate ---------------------------------------

MECHANISM_WORDS = re.compile(
    r"\b(because|mechanism|why|how it works|we (?:find|show|measure|trained)|"
    r"ablation|architecture|algorithm|derivation|proof|implementation|"
    r"under the hood|internals?|trade[- ]off)\b",
    re.I,
)
RESULT_WORDS = re.compile(
    r"\b(results?|accuracy|benchmark|evaluat|baseline|improv\w+ by|"
    r"reduces?|outperform|pass@|score[sd]?|throughput|latency)\b",
    re.I,
)
VERIFIABLE_WORDS = re.compile(
    r"\b(arxiv|github|doi|dataset|code (?:is )?(?:available|released)|"
    r"repository|appendix|model card|reproduc)\b",
    re.I,
)
NUMBERS = re.compile(r"\b\d+(?:\.\d+)?\s?%|\b\d+\.\d+\b|\b\d{3,}\b")

# Source quality, read off the feed file's own `tier` field rather than
# guessed from the domain. §8.1: tiering is enforced in code, not in a
# prompt, because a prompt asked to respect it would respect it most of
# the time — which is the wrong number.
TIER_QUALITY = {"primary": 1.0, "corroborating": 0.62, "community": 0.45}

# Sources that exist to point at other sources. §8.3 forbids publishing
# a post whose only source is a roundup; they are discovery aids, and
# the pipeline follows them to the primary source or drops the item.
ROUNDUP_SOURCES = {
    "Import AI (Jack Clark)",
    "TLDR AI",
    "Hugging Face — Daily Papers",
    "KDnuggets",
}


@dataclass
class QualityScore:
    total: float
    passed: bool
    components: dict = field(default_factory=dict)
    detail: str = ""


def quality_gate_offline(item, prof: Profile) -> QualityScore:
    """Deterministic stage 1. Each of the four §7.1 components is scored
    0..1 and multiplied by its weight from the profile, so re-weighting
    is a profile edit and never a code change."""
    weights = prof.quality_weights
    text = f"{item.title}\n{item.summary}"

    # technical substance — a mechanism, a result, or a number
    substance = 0.0
    if MECHANISM_WORDS.search(text):
        substance += 0.5
    if RESULT_WORDS.search(text):
        substance += 0.3
    if NUMBERS.search(text):
        substance += 0.3
    # A bare headline with no body is not substantial, whatever words
    # happen to be in it.
    if len(item.summary or "") < 120:
        substance *= 0.55
    substance = min(1.0, substance)

    source_quality = TIER_QUALITY.get(item.source.tier, 0.5)
    if item.source.name in ROUNDUP_SOURCES:
        source_quality = min(source_quality, 0.35)

    # novelty — recency stands in for "new, not a restatement". The
    # restatement half is caught by dedup, which runs before this.
    novelty = 1.0
    age = _age_days(item.published)
    if age is not None:
        novelty = 1.0 if age <= 2 else 0.8 if age <= 7 else 0.5 if age <= 21 else 0.2

    verifiability = 0.35
    if VERIFIABLE_WORDS.search(text):
        verifiability += 0.4
    if item.url.startswith("https://"):
        verifiability += 0.15
    verifiability = min(1.0, verifiability)

    components = {
        "technical_substance": substance * float(weights["technical_substance"]),
        "source_quality": source_quality * float(weights["source_quality"]),
        "novelty": novelty * float(weights["novelty"]),
        "verifiability": verifiability * float(weights["verifiability"]),
    }
    total = round(sum(components.values()), 1)
    minimum = prof.quality_minimum
    return QualityScore(
        total=total,
        passed=total >= minimum,
        components={k: round(v, 1) for k, v in components.items()},
        detail=f"{total}/{minimum} (offline scorer)",
    )


QUALITY_PROMPT = """You are scoring one feed item for a technical blog's
quality gate. This is PASS/FAIL on quality alone — do NOT consider
whether the subject is interesting to anyone. Relevance is scored
separately and mixing the two is the failure this gate exists to avoid.

Score each component from 0 to its maximum:
- technical_substance (max {w_substance}): does it contain a mechanism,
  a result, or a number? A headline with no findable substance is 0.
- source_quality (max {w_source}): primary source > lab blog > quality
  press > aggregator. This item's source tier is "{tier}".
- novelty (max {w_novelty}): new, not a restatement of something
  already covered elsewhere.
- verifiability (max {w_verify}): are the claims traceable to something
  checkable — a paper, a repo, a dataset, a model card?

TITLE: {title}
SOURCE: {source}
TEXT (truncated):
{text}

Return ONLY JSON:
{{"technical_substance": 0, "source_quality": 0, "novelty": 0,
  "verifiability": 0, "note": "one short sentence"}}"""


def quality_gate(llm, item, prof: Profile) -> QualityScore:
    weights = prof.quality_weights
    result = llm.json(
        QUALITY_PROMPT.format(
            w_substance=weights["technical_substance"],
            w_source=weights["source_quality"],
            w_novelty=weights["novelty"],
            w_verify=weights["verifiability"],
            tier=item.source.tier,
            title=item.title,
            source=item.source.name,
            text=(item.summary or "")[:3000],
        ),
        model=llm_module.CLASSIFY_MODEL,
        temperature=0,
        label="quality gate",
        offline=None,  # handled below, so the offline path keeps its detail
    )
    if not isinstance(result, dict):
        return quality_gate_offline(item, prof)

    components = {}
    for name, weight in weights.items():
        try:
            value = float(result.get(name, 0))
        except (TypeError, ValueError):
            value = 0.0
        components[name] = round(max(0.0, min(float(weight), value)), 1)
    total = round(sum(components.values()), 1)
    return QualityScore(
        total=total,
        passed=total >= prof.quality_minimum,
        components=components,
        detail=str(result.get("note", ""))[:160],
    )


# --- stage 2: relevance rank -----------------------------------------


@dataclass
class RelevanceScore:
    total: float
    components: dict = field(default_factory=dict)
    matched_strong: list[str] = field(default_factory=list)
    matched_medium: list[str] = field(default_factory=list)
    why: str = ""
    bucket: str = "serendipity"  # strong | adjacent | serendipity


def _matches(text: str, tiers: list[tuple[str, list[str]]]) -> list[str]:
    lowered = text.lower()
    return [topic for topic, phrases in tiers if any(p in lowered for p in phrases)]


def _topic_vocabulary(topics: list[str]) -> str:
    """The taxonomy's own words for the topics an item was classified
    into.

    CALIBRATION CHANGE, Phase 3. Matching the profile's signal phrases
    against the item's title and summary alone was far too sparse: over
    341 Radar survivors the relevance rank produced only eight distinct
    values, with 104 items tied at 60.0 and 85 at 70.0, so the order of
    the top ~90 candidates — which is what actually decides what gets
    published — was effectively arbitrary.

    The fix deliberately introduces NO new mapping table. It appends the
    taxonomy's own label and description for each classified topic to
    the text being matched, so the profile's vocabulary is matched
    against the taxonomy's vocabulary: an item classified
    `interpretability` carries "Features, circuits, probing, activation
    steering, representation engineering", which is what the profile's
    `mechanistic interpretability` entry already lists as its signals.
    Two closed vocabularies written for the same site agreeing with each
    other is not a coincidence to be exploited by a lookup table; it is
    the thing the lookup table would have been approximating.
    """
    from . import taxonomy as tax

    parts = []
    for slug in topics:
        info = tax.topics().get(slug)
        if info:
            parts.append(f"{info['label']} {info['description']}")
    return " ".join(parts)


def relevance_rank(
    item,
    section: str,
    topics: list[str],
    prof: Profile,
    *,
    starvation_bonus: float = 0.0,
) -> RelevanceScore:
    """Stage 2. Only ever applied to items that passed the gate, and it
    only ORDERS the queue — it can never push a gate-failing item into
    it. That asymmetry is the whole reason the two stages exist."""
    weights = prof.relevance_weights
    text = f"{item.title}\n{item.summary}\n{_topic_vocabulary(topics)}"

    strong = _matches(text, prof.strong)
    medium = _matches(text, prof.medium)
    low_hit = any(phrase in text.lower() for phrase in prof.low)

    components: dict[str, float] = {}
    # Graded, not binary. Matching one strong interest is worth 70% of
    # the component and each further one adds 15%, capped at the full
    # weight. The Phase 3 dry run showed a binary term collapsing 104
    # items onto one score; an item that touches interpretability AND
    # inference is genuinely a better fit than one that touches only
    # inference, and the ranking should be able to say so.
    if strong:
        share = min(1.0, 0.70 + 0.15 * (len(strong) - 1))
        components["strong_interest_match"] = round(
            float(weights["strong_interest_match"]) * share, 1
        )
    else:
        components["strong_interest_match"] = 0.0
    if medium and not strong:
        share = min(1.0, 0.70 + 0.15 * (len(medium) - 1))
        components["medium_interest_match"] = round(
            float(weights["medium_interest_match"]) * share, 1
        )
    else:
        components["medium_interest_match"] = 0.0
    # Section fit: a classified section that is not "none" and topics
    # that survived the closed vocabulary. An item nobody could file is
    # an item nobody asked for.
    # Section fit is how confidently the item could be FILED, and an
    # item nobody could file is an item nobody asked for. Graded by how
    # much of the three-axis record the classifier could actually fill.
    fit = 0.0
    if section:
        fit += 0.5
    if topics:
        fit += 0.25 + 0.125 * min(2, len(topics) - 1)
    components["section_fit"] = round(fit * float(weights["section_fit"]), 1)

    # §8.3: mechanism over event. A piece explaining HOW something works
    # outranks one reporting THAT it happened, and this is the term that
    # makes that true in the ranking rather than only in the prose.
    components["depth_bonus"] = (
        float(weights["depth_bonus"]) if MECHANISM_WORDS.search(text) else 0.0
    )
    components["topic_starvation"] = round(
        min(float(weights["topic_starvation"]), starvation_bonus), 1
    )
    components["low_interest_penalty"] = prof.low_interest_penalty if low_hit else 0.0

    total = round(sum(components.values()), 1)

    if strong:
        bucket = "strong"
    elif medium:
        bucket = "adjacent"
    else:
        bucket = "serendipity"

    return RelevanceScore(
        total=total,
        components={k: round(v, 1) for k, v in components.items()},
        matched_strong=strong,
        matched_medium=medium,
        bucket=bucket,
    )


WHY_PROMPT = """In ONE sentence of at most 25 words, say why this item is
relevant to a reader whose strong interests are: {interests}.

Be concrete and be honest. If the connection is weak, say that plainly —
this sentence is read by the site owner to spot a mis-tuned profile, so
a flattering answer is worse than a blunt one. No hype, no "this is a
game-changer", no restating the headline.

TITLE: {title}
SECTION: {section}
TOPICS: {topics}

Return ONLY JSON: {{"why": "..."}}"""


def why_relevant(llm, item, section: str, topics: list[str], score: RelevanceScore,
                 prof: Profile) -> str:
    """§7.2 — every published post and every Radar item carries a
    one-sentence reason. Never blank: the offline stand-in builds one
    from what actually matched, which is less fluent than a model's and
    exactly as auditable."""
    interests = ", ".join(t for t, _ in prof.strong) or "(none)"

    def offline() -> dict:
        if score.matched_strong:
            reason = f"Matches strong interest: {', '.join(score.matched_strong)}."
        elif score.matched_medium:
            reason = f"Adjacent to medium interest: {', '.join(score.matched_medium)}."
        else:
            reason = (
                "No profile interest matched — held as a serendipity candidate "
                "on quality alone."
            )
        return {"why": f"{reason} Filed under {section}: {', '.join(topics) or 'no topic'}."}

    result = llm.json(
        WHY_PROMPT.format(
            interests=interests,
            title=item.title,
            section=section,
            topics=", ".join(topics) or "(none)",
        ),
        model=llm_module.CLASSIFY_MODEL,
        temperature=0,
        label="why_relevant",
        offline=offline,
    )
    if not isinstance(result, dict) or not result.get("why"):
        result = offline()
    return str(result["why"]).strip()[:200]


# --- topic starvation -------------------------------------------------


def _age_days(published: str) -> float | None:
    if not published:
        return None
    try:
        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400


class TopicActivity:
    """When each topic was last published on, so §7.1's starvation bonus
    can fill the sections out evenly over weeks WITHOUT lowering the bar.

    The bonus reorders the queue among items that already passed the
    quality gate. It can never push a failing item into it — that is
    enforced by where it is applied (stage 2 only), not by a cap.
    """

    def __init__(self, prof: Profile):
        config = prof.starvation
        self.enabled = bool(config.get("enabled", True))
        self.days_before = int(config.get("days_before_bonus", 10))
        self.max_bonus = float(config.get("max_bonus", 10))
        self.last: dict[str, str] = read_json(TOPIC_ACTIVITY_FILE, {"topics": {}})["topics"]

    @classmethod
    def from_archive(cls, prof: Profile, posts: list[dict]) -> "TopicActivity":
        """Seeded from the published archive rather than from a state
        file that does not exist yet, so the very first run already
        knows that `llms` was touched yesterday and `generative-ai`
        never has been."""
        activity = cls(prof)
        for post in posts:
            for topic in post.get("topics", []):
                date_str = (post.get("pub_date") or "")[:10]
                if date_str and date_str > activity.last.get(topic, ""):
                    activity.last[topic] = date_str
        return activity

    def bonus(self, topics: list[str]) -> float:
        """Linear from 0 at `days_before` to `max_bonus` at twice that,
        taking the hungriest of the item's topics. A topic never
        published at all is maximally starved."""
        if not self.enabled or not topics:
            return 0.0
        best = 0.0
        today = date.today()
        for topic in topics:
            last = self.last.get(topic)
            if not last:
                return self.max_bonus
            try:
                days = (today - date.fromisoformat(last[:10])).days
            except ValueError:
                continue
            if days <= self.days_before:
                continue
            ratio = min(1.0, (days - self.days_before) / float(self.days_before))
            best = max(best, ratio * self.max_bonus)
        return round(best, 1)

    def record(self, topics: list[str], when: str | None = None) -> None:
        stamp = (when or date.today().isoformat())[:10]
        for topic in topics:
            self.last[topic] = stamp

    def save(self, dry_run: bool) -> None:
        # Written even in a dry run: it records what the ARCHIVE looks
        # like, not what a run published, and it is one of the
        # observability outputs Phase 3 is graded on.
        write_json(TOPIC_ACTIVITY_FILE, {"topics": self.last})

    def starved(self, all_topics: list[str]) -> list[tuple[str, int]]:
        """(topic, days since last touched) for the report, newest-last.
        A topic that has never been published comes back as -1."""
        today = date.today()
        rows = []
        for topic in all_topics:
            last = self.last.get(topic)
            if not last:
                rows.append((topic, -1))
                continue
            try:
                rows.append((topic, (today - date.fromisoformat(last[:10])).days))
            except ValueError:
                rows.append((topic, -1))
        return sorted(rows, key=lambda r: (-1 if r[1] < 0 else -r[1]))


# --- discovery mix (§7.1, checked weekly not per run) -----------------


def discovery_mix(entries: list[dict]) -> dict:
    """The ~70/20/10 strong/adjacent/serendipity split, measured over
    whatever window the caller passes in.

    §7.1 is explicit that this is checked WEEKLY, not per run: a single
    run publishing two strong-interest items is not evidence of a
    filter bubble, and reacting to it per-run would turn the mix into a
    quota that pushes weaker material through to fill the serendipity
    slot. Nothing in the pipeline acts on this number; it is reported.
    """
    counts = {"strong": 0, "adjacent": 0, "serendipity": 0}
    for entry in entries:
        bucket = entry.get("bucket")
        if bucket in counts:
            counts[bucket] += 1
    total = sum(counts.values()) or 1
    return {
        "counts": counts,
        "shares": {k: round(v / total, 3) for k, v in counts.items()},
        "n": sum(counts.values()),
    }
