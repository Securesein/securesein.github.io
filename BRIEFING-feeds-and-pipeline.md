# Briefing: feed sourcing for the Securesein "Model Updates" and "Benchmarks" channels

You are being asked to do two things:

1. **Primary task — find and verify sources for BOTH channels.** There are
   **two separate deliverables**, and neither is optional:

   - **`feeds-releases.json`** — sources for the **Model Updates** channel.
     These mostly *are* feeds: RSS/Atom, vendor changelog pages, Hugging Face
     Hub API endpoints. Schema in §6.1.
   - **`feeds-benchmarks.json`** — sources for the **Benchmarks** channel.
     **These are mostly NOT feeds.** Benchmark results live in datasets, git
     repositories, JSON APIs and Python client libraries, and should be
     ingested as structured data — never scraped out of rendered leaderboard
     HTML. Do not limit yourself to RSS here; if you only return RSS feeds
     for this half, you have not done the task. Schema in §6.2.

   Treat them as two independent research jobs with two independent outputs.
   The Benchmarks half is currently the weaker of the two and has the single
   highest-value gap in the whole system (§4.2), so do not shortchange it.

2. **Secondary task — challenge the design.** Both channels technically run
   but publish almost nothing. §3 and §4 give you the real numbers. If you
   think the sources aren't the bottleneck, say so and say what is.

Everything below is current as of 2026-10-02 and was read out of the live
repository and its GitHub Actions logs, not from memory.

---

## 1. The system in one paragraph

`securesein.github.io` is a static Astro site. A Python pipeline running in
GitHub Actions turns feeds into two kinds of output: **structured data**
(JSON records committed to the repo and rendered as tables) and **short
posts** (markdown in `src/content/blog/`). There is no database — every
piece of state is a file in git. Two reader-facing surfaces matter here:

- **`/model-updates`** — short, dense posts: "what is new in the model
  landscape". Currently empty.
- **`/benchmarks`** — a tracker **table** of benchmark measurements, with
  roundup posts underneath it. The table's explicit design goal is to show
  *vendor-reported* and *independently-measured* numbers side by side,
  distinguished by a badge rather than split into two tables. Currently the
  table has data but is ~4 weeks stale, and the vendor half is essentially
  empty (see §4.2).

## 2. Scope: what is being kept, what is being switched off

The project previously had five content channels plus two prototypes. All
of them are **disabled right now** because they were costing money without
producing output. Going forward only these two are kept, and both must run
**fully automatically and cheaply**:

| Channel | Workflow | What it produces |
|---|---|---|
| Model Updates | `.github/workflows/releases.yml` | short posts about model releases |
| Benchmarks | `.github/workflows/benchmarks.yml` | measurement records (data) + occasional roundup posts |

Dropped: the `research`, `security` and general `news` channels, plus two
"Reader" prototypes. Do not propose sources for those.

## 3. Current state: both channels run, neither produces anything

This is the problem you're helping with. The numbers are from real runs.

### 3.1 Model Updates — runs hourly, has never published a post

A representative run (2026-10-01 19:00 UTC, full output):

```
4 unseen item(s) across the release sources.
  0 classified as a release, 0 corroborating-only.
  0 candidate(s) at or above the threshold of 6.0.
  spend: 4 model call(s), ~$0.001 this run
```

Lifetime rejection reasons for this channel (`state/rejected.jsonl`):

| reason | count |
|---|---|
| `queue_expired` | 529 |
| `not_a_release` | 404 |
| `no_product_angle` | 115 |
| `below_threshold` | 40 |

The publication ledger contains **zero** entries for the `release` section,
and every run reports its section budget as `release: used 0, target 6`. So
the budget was never the constraint — the channel simply never produced a
publishable candidate.

Note the shape of the failure: of everything that reached the classifier,
the overwhelming majority was rejected as **not a release at all**, and only
40 items ever got far enough to be scored and fall below the threshold.

### 3.2 Benchmarks — runs daily, ingests data, but the data never changes

A representative run (last successful one, full output):

```
Ingesting benchmark measurements from 2025-01-01 onward.
  adapter epoch: 1263 measurement(s), 5 unresolved model name(s)
  upsert: 0 new, 46 superseded, 1263 unchanged, 1325 total.
  no triggers fired — data committed, no post. This is the normal case.
  spend: 0 model call(s), ~$0.000 this run
```

So: the adapter works, costs nothing, and returns the same 1263 rows every
day. **Zero new measurements.** The newest `measuredAt` date anywhere in the
collection is **2026-09-05**, roughly four weeks old. Exactly one roundup
post has ever been published (2026-09-28, triggered by `new_leader` and
`new_top5_entrant`), which proves the publishing path works when new data
actually lands.

## 4. How each channel decides to publish

You need this to judge whether a source you propose can ever reach a reader.

### 4.1 Model Updates

```
ingest → age filter (max 14 days) → seen-cursor dedup
      → LLM classifies "is this a release event?"   ← most rejections happen here
      → score against a weights table
      → threshold 6.0 → cap 2 posts/run, 10-day cooldown per model entity
```

**Tiering is enforced in code, not in a prompt.** Only a source with
`tier: "primary"` may trigger a post at all. `corroborating` sources can add
score but never trigger. `community` sources are context only.

Scoring weights (`config/releases.json`), threshold is 6:

```
primary_source            +3     open_weights             +2
event_new_model           +4     tier1_vendor             +1
event_version_bump_major  +3     non_tier1                -2
event_version_bump_minor  +1     benchmark_claims_present +1
event_capability_update   +2     corroborated_48h         +1
event_deprecation         +2     press_release_only       -3
event_availability        +1     no_product_angle         -3
                                 entity_in_cooldown       -5
```

Tier-1 vendors are: openai, anthropic, google, meta, microsoft, mistral,
nvidia. The config file flags `non_tier1: -2` in its own comments as "THE
SINGLE MOST LIKELY NUMBER IN THIS FILE TO BE WRONG — if the channel goes
quiet on the Chinese open-weights labs, this is why". Worth your opinion.

Two high-volume sources (Azure updates, AWS What's New) are keyword-filtered
before scoring or they drown everything else.

### 4.2 Benchmarks

```
adapters → normalise to the collection schema
        → resolve the model name against models.json (a CLOSED vocabulary of
          250 models; an unresolved name is parked for a human, never
          auto-registered, never written into the collection)
        → upsert measurements           ← this is free and is the main point
        → evaluate post triggers
        → draft one roundup if the fired triggers total ≥ 4
```

Committing measurements costs no post budget and no model calls. Only a
roundup costs anything. Trigger weights (`config/benchmarks.json`):

```
benchmark_erratum_or_retraction  5
new_leader                       4     ← alone, clears the threshold
vendor_vs_thirdparty_gap         4     ← alone, clears the threshold
new_top5_entrant                 2
first_measurement_of_tier1_model 2
threshold                        4     max 2 roundups/week
```

**The most important finding in this whole document:** `vendor_vs_thirdparty_gap`
fires when a vendor's own published claim and an independent measurement for
the *same model on the same benchmark* differ by ≥5 percentage points. It is
described in the config as "the single most valuable thing this channel can
produce". It has never fired, and it structurally cannot, because:

```
measuredBy distribution across all 1325 records:
  thirdparty   683
  community    640
  vendor         2      ← two
```

There are essentially **no vendor-claimed numbers in the collection**. The
highest-value trigger is dead, and the `/benchmarks` table's entire reason to
exist — showing the vendor's claim next to the independent number — has
nothing to display. **Sourcing vendor-published benchmark claims in a
machine-readable way is the highest-value thing you can deliver.**

Benchmark coverage today (records per benchmark):

```
frontiermath 337 · terminal-bench 326 · gpqa-diamond 312 · arc-agi-2 173
aider-polyglot 53 · hle 48 · swe-bench-verified 35 · livebench 21 · osworld 20
```

Three tracked benchmarks have **no adapter and therefore no rows at all**:
**MMLU-Pro**, **LMArena Text Elo**, **LiveCodeBench**.

## 5. What already exists — do not just duplicate it

- **`feeds-releases.json`** — 44 entries already. Covers: OpenAI (news, release
  notes, API changelog), Anthropic (docs release notes, SDK), Google (Gemini
  API changelog, Vertex AI, Developers Blog), Meta (llama-models releases),
  xAI, Microsoft (Azure updates, MSR blog), AWS What's New, Mistral, NVIDIA
  NeMo, Ai2 OLMo, Qwen blog, DeepSeek API news, plus ~18 Hugging Face org
  endpoints (Qwen, DeepSeek, Moonshot, Z.ai, MiniMax, ByteDance-Seed, Tencent,
  Baidu, OpenAI, Microsoft, NVIDIA, Mistral, Google, meta-llama, IBM Granite,
  Ai2, LiquidAI, RekaAI, Cohere), plus corroborating serving-stack feeds
  (vLLM, llama.cpp, Ollama, Transformers, SGLang).
- **`feeds-benchmarks.json`** — ~20 entries, but only **one adapter is actually
  built**: Epoch AI. Everything else is recorded intent.
- **`models.json`** — 250-model closed registry, seeded from Epoch's CC-BY
  catalogue.

Tell me which existing entries are **dead weight or wrong**, as well as what
is missing. One is already known to be broken (§7.1).

## 6. Output schema — this part is strict

The loader reads these fields and ignores everything else. Anything you
invent that isn't in this list is documentation, not configuration.

### 6.1 Release sources (`feeds-releases.json`)

```json
{
  "naam": "OpenAI — News",
  "url": "https://openai.com/news/rss.xml",
  "type": "rss",
  "tier": "primary",
  "vendor": "openai",
  "verified": true,
  "inScope": true,
  "note": "What this source is good for, and any filtering it needs."
}
```

### 6.2 Benchmark sources (`feeds-benchmarks.json`)

```json
{
  "naam": "Epoch AI — Benchmarking Hub",
  "url": "https://epoch.ai/benchmarks",
  "type": "python_client",
  "role": "measurement",
  "measuredBy": "thirdparty",
  "tier": "primary",
  "verified": true,
  "license": "CC-BY — attribution required in the rendered table",
  "note": "..."
}
```

### 6.3 Allowed field values

| field | values | meaning |
|---|---|---|
| `type` | **`rss`, `atom`, `hf_api`, `json`, `html`** | these five have working adapters |
| `type` | `api`, `git`, `python_client` | **skipped at runtime** — needs a bespoke adapter written first |
| `tier` | `primary` / `corroborating` / `community` | only `primary` may trigger a post |
| `role` | `measurement` / `finding` | `finding` can never write a number into the table |
| `measuredBy` | `vendor` / `thirdparty` / `community` | who ran the eval — drives the badge and the gap trigger |
| `inScope` | `true` / `false` | **exact camelCase spelling** (see §7.1) |
| `verified` | `true` / `false` | `true` only if you actually fetched it |

If you propose a source whose `type` is `api`, `git` or `python_client`,
**also describe the adapter** — what exact URL/endpoint returns the data, in
what format, and how to get from that to the record schema. Otherwise it
will sit in the file doing nothing, which is what most of
`feeds-benchmarks.json` is today.

### 6.4 What "verified" has to mean

For every source you propose, report: HTTP status, whether it parsed, the
**number of items returned**, and the **date of the newest item**. A feed
that returns 200 and 15 items whose newest entry is from 2022 is a dead
blog, and that has already happened here more than once.

## 7. Known defects — confirm or correct these

### 7.1 A real bug: `in_scope` vs `inScope`

The loader reads `row.get("inScope", True)`. But `feeds-releases.json` marks
its one disabled entry with `"in_scope": false` (snake_case), while
`feeds-benchmarks.json` uses `"inScope": false` (camelCase). **The snake_case
one is silently ignored**, which is why the Meta AI Blog entry — explicitly
marked out of scope because its URL 404s — is still being fetched every
single hour and still logs `Meta AI — Blog: HTTP 404`. Use camelCase.

### 7.2 Sources that failed on the last live run

These produced HTTP errors during real runs and need either a replacement
URL or removal: `Meta AI — Blog` (404), `Import AI / Jack Clark` (403),
`VentureBeat AI` (429), `AI News` (403/202), `MarkTechPost` (403/202),
`EleutherAI Blog` (404), `Epoch AI` substack (403).

## 8. Questions I actually want your opinion on

Ranked by how much they matter.

1. **Vendor benchmark claims.** Where can a vendor's *own* published
   benchmark numbers be obtained machine-readably and durably — model cards,
   system cards, HF model-card metadata, structured tables in launch posts,
   something else? This unlocks the single most valuable trigger in the
   system and the `/benchmarks` table's whole premise. What would the record
   look like, and how do you tie a vendor's number to the same
   `(model, benchmark, metric)` key an independent measurement uses?
2. **Is Epoch stale, or is our pull wrong?** Our newest row is 2026-09-05 and
   daily pulls return "0 new". Is Epoch genuinely not publishing, or are we
   querying it in a way that misses recent additions?
3. **Release detection method.** Right now an LLM reads prose and answers
   "is this a release?", and it says no 404 times out of ~560. Would
   detecting releases from *structured* signals instead be more reliable —
   e.g. new repo IDs appearing on the HF Hub API with a `createdAt`, or a new
   row in a vendor's changelog page — with the model used only to write the
   post, not to decide whether there is one?
4. **Cadence.** Model Updates runs **hourly** and sees ~4 new items per run.
   Model releases are rare events. Is 2–4×/day better, both for cost and for
   giving the batch enough context to judge?
5. **Dead weight.** Which of the 44 existing release sources would you drop?
6. **The three missing benchmarks.** Is there a machine-readable source for
   MMLU-Pro, LMArena Text Elo and LiveCodeBench, or should they be removed
   from the tracked list rather than shown as permanently empty?

## 9. Hard constraints

- **Cost.** There are enforced ceilings: 150 model calls or $1.50 per run,
  $0.75/day, $3/week, $10/month. These exist because of a real incident and
  are not negotiable. The Benchmarks channel currently costs **$0.00** per
  run because ingesting data needs no model calls — that property is worth
  protecting. Prefer sources that need no model call to interpret.
- **No paid API keys.** Public, tokenless endpoints strongly preferred.
  (`Artificial Analysis` is explicitly parked for this reason, pending the
  owner reading their terms — do not revive it unilaterally.)
- **Licensing is honoured.** Epoch's data is CC-BY and the attribution is
  rendered on the page. Any source whose terms forbid republishing numbers
  must be flagged, not quietly ingested.
- **Durability over freshness.** This runs unattended. A fragile scrape of a
  JS-rendered leaderboard that breaks in a month is worse than nothing,
  because a broken adapter is logged and ignored rather than fixed.
- **No databases, no services.** Everything is files in git.
