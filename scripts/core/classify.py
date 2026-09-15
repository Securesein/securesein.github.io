"""
Turning a feed item into the five structured facts the Releases channel
scores on: eventType, vendor, family, version, openWeights, modality.

Two implementations of the same contract.

**The model classifier** is the live path: a cheap model, a strictly
enum-constrained JSON schema, temperature 0. Anything it returns that
is outside the enum, or that the registry cannot resolve, becomes
eventType "none" and the item is dropped. The enum is enforced here in
code after the call, not just asked for in the prompt.

**The deterministic classifier** is what runs with --offline-llm, and
it is a real implementation rather than a stub. Release announcements
are an unusually regular genre — "Introducing X", "X is now generally
available", "We are deprecating Y on <date>" — and a few dozen patterns
get most of them right. It exists so the scoring rubric, the entity
dedup and the budget logic can be exercised end to end against real
feed data with no API spend and no week of waiting, which is exactly
what Phase 3 has to demonstrate.

It is deliberately *conservative*: where it is unsure it returns "none"
and the item is dropped with a logged reason, because a dropped release
costs one missing post and a wrongly-classified one costs a wrong post
published without review.
"""

from __future__ import annotations

import re
import sys

from .registry import Registry

EVENT_TYPES = (
    "new_model",
    "version_bump",
    "availability",
    "deprecation",
    "capability_update",
)
MODALITIES = ("text", "vision", "audio", "video", "embedding")
NONE = "none"

# --- deterministic patterns -----------------------------------------

DEPRECATION = re.compile(
    r"\b(deprecat|sunset|retir(e|ing|ement)|end[- ]of[- ]life|"
    r"shutting down|discontinu|will be removed|no longer available)\b",
    re.I,
)
AVAILABILITY = re.compile(
    r"\b(generally available|now available|general availability|\bGA\b|"
    r"now in preview|public preview|now supports? (?:the )?region|"
    r"expands? to|new region|price (?:cut|drop|reduction)|pricing update|"
    r"now on|available (?:in|on|to)|rolling out)\b",
    re.I,
)
CAPABILITY = re.compile(
    r"\b(now supports?|adds? support|brings? support|context window|"
    r"longer context|tool use|function calling|structured outputs?|"
    r"vision support|audio input|batch api|caching|fine[- ]tuning)\b",
    re.I,
)
INTRODUCING = re.compile(
    r"\b(introducing|announcing|meet|we(?:'re| are) (?:releasing|launching)|"
    r"say hello to|welcome)\b",
    re.I,
)
OPEN_WEIGHTS = re.compile(
    r"\b(open[- ]weights?|open[- ]source|apache[- ]2|mit licen[cs]e|"
    r"weights (?:are )?(?:now )?(?:available|released)|on hugging face)\b",
    re.I,
)

MODALITY_HINTS = {
    "vision": re.compile(r"\b(vision|image|multimodal|visual|ocr|screenshot)\b", re.I),
    "audio": re.compile(r"\b(audio|speech|voice|tts|asr|transcription)\b", re.I),
    "video": re.compile(r"\b(video|frames?|clip generation)\b", re.I),
    "embedding": re.compile(r"\b(embedding|embeddings|retrieval model|reranker)\b", re.I),
}

# A version is a dotted or dashed number attached to a name, and a
# trailing date stamp ("-2026-09-03") is a version too — it is how
# OpenAI and Anthropic name their snapshots.
VERSION = re.compile(
    r"\b(?:v|version\s*)?(\d+(?:\.\d+){0,3})\b|\b(\d{4}-\d{2}-\d{2})\b", re.I
)

# The serving and tooling layer. These ship constantly and none of it
# is a model release, however many model names the notes contain.
RUNTIME_RELEASE = re.compile(
    r"\b(ollama|vllm|llama\.cpp|sglang|transformers|tensorrt|triton|"
    r"text-generation-inference|\btgi\b|lm ?studio|koboldcpp|exllama|"
    r"sdk|cli|python client|node client|extension|plugin)\b",
    re.I,
)

PRESS_RELEASE = re.compile(
    r"\b(partners? with|partnership|collaborat(?:e|ion)|series [a-e]\b|"
    r"funding round|valuation|raises \$|appoints?|names? .* as|"
    r"joins the board|customer story|case study|webinar|summit|conference)\b",
    re.I,
)

# Benchmark names worth noticing in a vendor claim, in the loose
# spellings vendors actually use. Only used as a signal that numbers are
# being claimed; the numbers themselves are extracted elsewhere.
BENCHMARK_CLAIM = re.compile(
    r"\b(gpqa|frontiermath|swe[- ]bench|terminal[- ]bench|arc[- ]agi|"
    r"livebench|aider|humanity'?s last exam|\bhle\b|mmlu|lmarena|"
    r"livecodebench|osworld|benchmark|state[- ]of[- ]the[- ]art|\bsota\b)\b",
    re.I,
)


def has_benchmark_claim(text: str) -> bool:
    """A benchmark *name* near a *number* — either alone is too loose.
    "beats the benchmark" with no figure is marketing; "74.2% on
    SWE-bench Verified" is a claim that can be checked and cross-written
    into the measurements collection."""
    if not BENCHMARK_CLAIM.search(text or ""):
        return False
    return bool(re.search(r"\d+(?:\.\d+)?\s?%|\b\d+\.\d+\b|\bELO\b", text or "", re.I))


def _modalities(text: str) -> list[str]:
    found = [name for name, pattern in MODALITY_HINTS.items() if pattern.search(text)]
    # Text is assumed unless the item is plainly about something else;
    # every model in scope here reads and writes text.
    return ["text", *found] if found else ["text"]


def _version_from(text: str) -> str:
    """The version attached to a name, not the first number in the
    sentence — "GPT-6 Astra" is version 6, and a summary that also says
    "1.05 million tokens" must not turn that into 1.05.

    Callers pass the *model's own name* here wherever one has been
    resolved, precisely so the number comes from the identity rather
    than from the prose around it.
    """
    for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        return match.group(1)
    match = re.search(r"[A-Za-z][\w.]*[\s\-]v?(\d+(?:\.\d+){0,3})(?![\w.])", text)
    return match.group(1) if match else ""


def is_major(version: str) -> bool:
    """"5.0" and "6" are major; "5.1" and "2026-09-03" are not. A major
    bump is worth three points and a minor one is worth one, so this
    distinction is doing real work."""
    if not version or "-" in version:
        return False
    parts = version.split(".")
    if len(parts) == 1:
        return True
    return all(p == "0" for p in parts[1:])


# How close a registry entry's own release date has to be to an item's
# timestamp for the item to read as that model's announcement rather
# than as later coverage or a capability note. Wide enough to absorb a
# slow feed and a timezone, narrow enough that a six-month-old model
# being mentioned again is not a new release.
RELEASE_WINDOW_DAYS = 14


def deterministic(item, registry: Registry) -> dict:
    """The offline classifier. Returns the same shape the model does."""
    title = item.title or ""
    body = item.summary or ""
    text = f"{title}\n{body}"
    vendor = item.source.vendor if item.source.vendor not in ("", "-") else ""

    # A Hugging Face repo appearing under a tracked org is the clearest
    # signal in the whole channel: a first-party, timestamped release
    # from a lab with no usable RSS (brief §10).
    if item.source.type == "hf_api":
        repo_name = title.split("/")[-1]
        model = registry.resolve_model(repo_name)
        # An unregistered repo is NOT a family invented on the spot. A
        # tracked org publishes research artefacts, safety classifiers,
        # diffusion checkpoints and tokenizer experiments alongside its
        # models; minting a family id from every repo name is precisely
        # the silent auto-registration §4.1 forbids. No registry entry,
        # no family — the caller parks the name and drops the item.
        return {
            "eventType": "new_model",
            "vendor": model.vendor if model else "",
            "family": model.family if model else "",
            "version": _version_from(model.display_name if model else repo_name),
            "openWeights": True,  # it is a public weights repo
            "modality": _modalities(text),
            "modelHint": repo_name,
            "classifier": "deterministic/hf",
        }

    # The headline names the subject; the body names everything the
    # subject is being compared against. Resolving from the body first
    # is how "Introducing GPT-6 Astra ... 47% faster than GPT-5.6 Sol"
    # ends up filed under GPT-5.6 Sol.
    model = _first_known_model(title, registry) or _first_known_model(body, registry)
    family = model.family if model else ""
    # The version comes off the model's own name wherever one resolved,
    # so a context window of "1.05 million" can never become a version.
    version = _version_from(model.display_name if model else title)
    if model:
        # The registry wins over the feed's own `vendor` field. A Vertex
        # AI release note is tagged vendor=google but can be announcing a
        # DeepSeek model, and an entity key of google/deepseek is not a
        # key, it is two different facts glued together.
        vendor = model.vendor

    if RUNTIME_RELEASE.search(title):
        # Brief §10: runtime and serving releases are not model
        # releases. An Ollama point release whose notes happen to name a
        # brand-new model is exactly the item this channel exists to
        # suppress, and leaving that to source tiering alone would mean
        # one mis-tiered feed entry could publish it.
        event = NONE
    elif DEPRECATION.search(text):
        event = "deprecation"
    elif model is not None and _is_fresh_release(model, item):
        # The registry says this model was published within days of this
        # item. That is a release announcement, whatever words the
        # headline happens to use.
        event = "new_model"
    elif INTRODUCING.search(title):
        event = "new_model" if model is None or not version else "version_bump"
    elif AVAILABILITY.search(title):
        event = "availability"
    elif CAPABILITY.search(title):
        event = "capability_update"
    elif AVAILABILITY.search(body):
        event = "availability"
    elif CAPABILITY.search(body):
        event = "capability_update"
    elif model is not None and version:
        event = "version_bump"
    else:
        event = NONE

    return {
        "eventType": event,
        "vendor": vendor,
        "family": family,
        "version": version,
        "openWeights": bool(OPEN_WEIGHTS.search(text)) or (model.open_weights if model else False),
        "modality": _modalities(text),
        "modelHint": model.display_name if model else "",
        "classifier": "deterministic",
    }


def _is_fresh_release(model, item) -> bool:
    if not model.released_at or not item.published:
        return False
    from datetime import date, timedelta

    try:
        released = date.fromisoformat(model.released_at[:10])
        seen = date.fromisoformat(item.published[:10])
    except ValueError:
        return False
    return abs((seen - released).days) <= RELEASE_WINDOW_DAYS


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _first_known_model(text: str, registry: Registry):
    """The longest registry name appearing in the text wins, so "Claude
    Opus 4.8" beats "Claude" and the family is not flattened. Ties go to
    the name that appears earliest, which in a headline is the subject.
    """
    lowered = (text or "").lower()
    if not lowered:
        return None
    best = None
    best_key = (0, len(lowered) + 1)  # (length, -position) as a sort key
    for model in registry.models.values():
        for name in (model.display_name, *model.aliases):
            if not name or len(name) < 4:
                continue
            position = lowered.find(name.lower())
            if position == -1:
                continue
            if (len(name), -position) > (best_key[0], -best_key[1]):
                best, best_key = model, (len(name), position)
    return best


# --- the model classifier -------------------------------------------

PROMPT = """You are classifying one item from an AI vendor's feed for a
release tracker. Decide what KIND of event it is, and extract the model
it is about.

eventType MUST be exactly one of:
- "new_model"          a model that did not exist before
- "version_bump"       a new version of an existing model family
- "availability"       GA, a new region, new pricing, a new provider
- "deprecation"        a model being retired or sunset
- "capability_update"  new modality, context length or tool support on
                       an existing model
- "none"               anything else at all: tooling releases, SDK
                       point releases, partnerships, funding, hiring,
                       conference talks, customer stories, research
                       papers with no shipped model.

Be strict. "none" is the right answer far more often than any other.
A runtime or serving release (vLLM, llama.cpp, Ollama, transformers) is
ALWAYS "none" — those are not model releases.

TITLE: {title}
SOURCE: {source}
TEXT (truncated):
{text}

Return ONLY JSON:
{{"eventType": "...", "vendor": "...", "family": "...",
  "version": "...", "openWeights": true|false,
  "modality": ["text"], "modelHint": "the model's name as written"}}"""


def classify(llm, item, registry: Registry, model_name: str) -> dict:
    """Live path with the deterministic classifier as its offline
    stand-in. The enum is enforced here rather than trusted to the
    prompt: anything outside it becomes "none"."""
    result = llm.json(
        PROMPT.format(
            title=item.title,
            source=item.source.name,
            text=(item.summary or "")[:3000],
        ),
        model=model_name,
        temperature=0,
        label="release classifier",
        offline=lambda: deterministic(item, registry),
    )
    if not isinstance(result, dict):
        return {"eventType": NONE, "classifier": "failed"}

    event = str(result.get("eventType", NONE))
    if event not in EVENT_TYPES:
        result["eventType"] = NONE
    modality = [m for m in (result.get("modality") or []) if m in MODALITIES]
    result["modality"] = modality or ["text"]
    result["openWeights"] = bool(result.get("openWeights"))
    result.setdefault("classifier", "model")
    for key in ("vendor", "family", "version", "modelHint"):
        result[key] = str(result.get(key) or "")
    return result


# ===================================================================
# Section / format / topic classification (brief §7, the three axes)
# ===================================================================
#
# Distinct from the release classifier above, which answers "what kind
# of release event is this?". This one answers the three IA questions:
#
#   section  why would someone read this?
#   format   what shape is this piece?
#   topics   what is it technically about?
#
# Same contract as the release classifier and for the same reason: the
# enums are enforced HERE IN CODE after the call, not merely asked for
# in the prompt. Anything outside the closed vocabulary in
# /taxonomy.json is dropped, never coerced onto the nearest neighbour,
# and an item with no valid topic left is not published at all.
#
# The deterministic implementation is what runs with --offline-llm. It
# is a real classifier, not a stub: section and topic assignment out of
# a feed item is unusually pattern-rich (an arXiv cs.CR paper about
# prompt injection is not an ambiguous case), and it is what makes the
# whole rubric replayable against real feed data with no API spend.

from . import taxonomy as tax  # noqa: E402

# --- section signals -------------------------------------------------
#
# Ordered by specificity: Security before Research, because a reward-
# hacking paper is a Security item under §8.4 even though it arrives
# from an ML venue and reads like a result. Benchmarks before Research
# for the same reason.

SECTION_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    # §8.4 — attacks, incidents and failure modes, INCLUDING reward
    # hacking and specification gaming, which the brief moves here out
    # of Research explicitly.
    ("security", re.compile(
        r"\b(prompt injection|jailbreak|jail[- ]break|guardrail|abliterat|"
        r"adversarial (?:example|attack|input|perturbation|robustness)|"
        r"exfiltrat|data leakage|memoriz|poison|backdoor|"
        r"supply chain|malicious|exploit|vulnerab|\bCVE\b|attack|threat|"
        r"hijack|sandbox escape|red[- ]team|reward hacking|specification gaming|"
        r"spec gaming|deceptive alignment|sabotage|scheming|"
        r"unsafe|misuse|abuse)\b", re.I)),
    # §8.2 — measured numbers with stated conditions.
    ("benchmark", re.compile(
        r"\b(leaderboard|benchmark results|contaminat|construct validity|"
        r"evaluation harness|eval harness|gpqa|frontiermath|swe[- ]bench|"
        r"terminal[- ]bench|arc[- ]agi|livebench|aider polyglot|mmlu|"
        r"livecodebench|osworld|lmarena|humanity'?s last exam)\b", re.I)),
    # §8.1 — a vendor saying a model exists. The release classifier
    # above is the authority here; this pattern only catches the
    # obvious ones for items that never went through it.
    ("release", re.compile(
        r"\b(introducing|announcing|now available|generally available|"
        r"we(?:'re| are) releasing|release notes|deprecat|sunset|"
        r"model card|open[- ]weights? release)\b", re.I)),
    # Fundamentals is NOT feed-driven (§8.6) — it is written from the
    # Radar and the benchmarks collection when a concept keeps
    # recurring. Nothing classifies into it from a feed item, which is
    # why there is no explainer pattern here.
]

# Research is the fallback, matching §3.4's own rule for unmappable
# items: anything that passed the quality gate and matched no section
# pattern is a Research candidate rather than a drop.
FALLBACK_SECTION = "research"

# --- topic signals ---------------------------------------------------
#
# One pattern per slug in taxonomy.json. A slug with no pattern can
# never be assigned, so this dict is asserted complete at import time
# rather than silently under-covering the vocabulary.

TOPIC_PATTERNS = {
    "llms": re.compile(
        r"\b(llm|language model|gpt|claude|gemini|llama|mistral|qwen|"
        r"deepseek|transformer|token|context window|chatbot)\b", re.I),
    "reasoning": re.compile(
        r"\b(reasoning|chain[- ]of[- ]thought|\bcot\b|test[- ]time compute|"
        r"thinking|deliberat|o1|planning|math(?:ematical)? problem|proof)\b", re.I),
    "agents": re.compile(
        r"\b(agent|agentic|tool use|tool[- ]calling|function calling|\bmcp\b|"
        r"model context protocol|multi[- ]agent|autonomous|orchestrat|"
        r"coding assistant|subagent|skill)\b", re.I),
    "interpretability": re.compile(
        r"\b(interpretab|mechanistic|circuit|sparse autoencoder|\bsae\b|"
        r"probing|activation steering|residual stream|feature direction|"
        r"representation engineering|refusal direction|attribution)\b", re.I),
    "deep-learning": re.compile(
        r"\b(neural network|gradient descent|backprop|loss landscape|"
        r"optimiz|scaling law|architecture|convolution|attention mechanism|"
        r"batch norm|regulariz|generaliz)\b", re.I),
    "reinforcement-learning": re.compile(
        r"\b(reinforcement learning|\brl\b|rlhf|rlvr|reward model|"
        r"policy optimi|\bgrpo\b|\bppo\b|\bdpo\b|q[- ]learning|"
        r"exploration|bandit)\b", re.I),
    "multimodal": re.compile(
        r"\b(multimodal|vision[- ]language|\bvlm\b|image|audio|speech|"
        r"video|\bocr\b|\btts\b|\basr\b|cross[- ]modal|visual)\b", re.I),
    "training": re.compile(
        r"\b(pre[- ]?train|fine[- ]?tun|training data|dataset|curriculum|"
        r"tokeniz|\bbpe\b|distill|continued training|post[- ]training|"
        r"instruction tuning|data mixture)\b", re.I),
    "inference": re.compile(
        r"\b(inference|serving|quantiz|\bgguf\b|llama\.cpp|ollama|\bvllm\b|"
        r"\bsglang\b|speculative decoding|kv cache|latency|throughput|"
        r"on[- ]device|edge|local(?:ly)? run|\bvram\b|batching|cost per token)\b", re.I),
    "evaluation": re.compile(
        r"\b(evaluat|benchmark|contaminat|held[- ]out|construct validity|"
        r"harness|leaderboard|replicat|reproduc|negative result|"
        r"ablation study|metric)\b", re.I),
    "ai-security": re.compile(
        r"\b(prompt injection|jailbreak|guardrail|exfiltrat|adversarial|"
        r"attack|exploit|vulnerab|supply chain|hijack|red[- ]team|"
        r"memoriz|data leakage|malicious|\bcve\b|threat model|sandbox)\b", re.I),
    "ai-safety": re.compile(
        r"\b(alignment|safety|deception|deceptive|honest|refusal|"
        r"reward hacking|specification gaming|scheming|sandbagging|"
        r"model welfare|dangerous capabilit|misuse|oversight|"
        r"constitutional ai)\b", re.I),
    "generative-ai": re.compile(
        r"\b(diffusion|image generation|text[- ]to[- ]image|"
        r"text[- ]to[- ]video|generative model|\bgan\b|flow matching|"
        r"stable diffusion|midjourney|sora|veo)\b", re.I),
}

_missing = set(tax.topic_slugs()) - set(TOPIC_PATTERNS)
if _missing:  # pragma: no cover - a vocabulary edit without a pattern
    raise RuntimeError(
        "taxonomy.json defines topics with no classifier pattern in "
        f"core/classify.py: {sorted(_missing)}. A topic that can never be "
        "assigned is worse than no topic — add a pattern or remove the slug."
    )

# --- format signals --------------------------------------------------

PAPER_SOURCES = re.compile(r"arxiv|openreview|\bjmlr\b|daily papers", re.I)
PAPER_WORDS = re.compile(
    r"\b(we (?:propose|present|introduce|show|find)|this paper|our method|"
    r"abstract:|preprint)\b", re.I)


def deterministic_axes(item) -> dict:
    """The offline classifier for the three axes.

    Deliberately conservative in one direction only: it will fall back
    to Research rather than drop an item, because the Radar is where
    unsure items belong and dropping is what the quality gate is for.
    """
    text = f"{item.title}\n{item.summary}"

    # THE CHANNEL DOES NOT GET A VOTE. An earlier version let a channel
    # pass a hint used as the fallback section, and the consequence was
    # immediate and instructive in the Phase 3 dry run: the security
    # channel claimed 364 of 381 gate survivors, because every item no
    # pattern matched fell back to "security" simply because the
    # security channel was the one that happened to fetch it. Its top
    # candidate was a diffusion-models tutorial.
    #
    # The fallback is §3.4's own rule and is the same for every caller:
    # anything unclassifiable is a Research candidate.
    section = ""
    for slug, pattern in SECTION_PATTERNS:
        if pattern.search(text):
            section = slug
            break
    if not tax.is_section(section):
        section = FALLBACK_SECTION

    topics = [slug for slug, pattern in TOPIC_PATTERNS.items() if pattern.search(text)]
    # Ordering matters: the schema takes at most three, and the first
    # three matches in vocabulary order are arbitrary. Prefer the most
    # specific — the ones whose pattern matched most distinctly — by
    # counting matches, with vocabulary order as the tie-break.
    topics.sort(key=lambda s: -len(TOPIC_PATTERNS[s].findall(text)))
    topics = tax.valid_topics(topics)

    if PAPER_SOURCES.search(item.source.name) or PAPER_WORDS.search(text):
        fmt = "paper"
    elif section == "benchmark":
        fmt = "benchmark"
    else:
        fmt = "news"

    return {
        "section": section,
        "format": fmt,
        "topics": topics,
        "classifier": "deterministic",
    }


AXES_PROMPT = """You are filing one item for a blog with three
orthogonal axes. Answer all three. Use ONLY the exact slugs listed.

SECTION — why would someone read this? Pick exactly one:
{sections}

Two placement rules that override the obvious reading:
- Reward hacking and specification gaming are SECURITY, not research.
  They are failure modes, not results.
- A defensive tooling release is rarely worth a post on its own; the
  ATTACK CLASS it responds to is. A new probe family is security; a
  scanner's point release is not.
- "explainer" (Fundamentals) is NEVER correct for a feed item. Those
  are written from accumulated material, not from the news.

FORMAT — what shape is this piece? Pick exactly one:
{formats}

TOPICS — what is it technically about? Pick 1, or up to 3 if they
genuinely all apply. This list is CLOSED: use the exact slug, do NOT
invent one, do NOT return a label, and do NOT return a topic that is
merely adjacent. Anything not on this list is discarded, and an item
with no valid topic left is not published at all.
{topics}

TITLE: {title}
SOURCE: {source} (tier: {tier})
TEXT (truncated):
{text}

Return ONLY JSON:
{{"section": "...", "format": "...", "topics": ["..."]}}"""


def classify_axes(llm, item) -> dict:
    """Live path with the deterministic classifier as its offline
    stand-in. Every returned value is re-checked against the closed
    vocabulary here; nothing is trusted because the prompt asked."""
    result = llm.json(
        AXES_PROMPT.format(
            sections=tax.section_prompt_block(),
            formats=tax.format_prompt_block(),
            topics=tax.topic_prompt_block(),
            title=item.title,
            source=item.source.name,
            tier=item.source.tier,
            text=(item.summary or "")[:3000],
        ),
        model=llm_module_classify_model(),
        temperature=0,
        label="axes classifier",
        offline=lambda: deterministic_axes(item),
    )
    if not isinstance(result, dict):
        return deterministic_axes(item)

    section = str(result.get("section") or "")
    if not tax.is_section(section) or section == "explainer":
        # Fundamentals is not feed-driven (§8.6); a classifier that says
        # so is wrong rather than interesting.
        section = FALLBACK_SECTION

    fmt = str(result.get("format") or "")
    if not tax.is_format(fmt):
        fmt = "news"
    # Schema refinement 6: a benchmark-shaped piece belongs in the
    # Benchmarks section. Enforced here so a draft can never be written
    # in a shape the build will reject.
    if fmt == "benchmark" and section != "benchmark":
        fmt = "news"

    topics = tax.valid_topics(result.get("topics"))
    dropped = [t for t in (result.get("topics") or []) if t not in topics]
    for slug in dropped:
        print(f"    Dropping invented topic {slug!r}.", file=sys.stderr)

    return {
        "section": section,
        "format": fmt,
        "topics": topics,
        "classifier": "model",
    }


def llm_module_classify_model() -> str:
    from . import llm as _llm

    return _llm.CLASSIFY_MODEL
