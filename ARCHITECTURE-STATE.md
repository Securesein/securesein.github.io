# Securesein — where the system actually stands

Written 2026-10-03, from the live repository, its GitHub Actions history
and its state files. Not from memory, and not from the design documents:
where the two disagree, this records what is running.

The purpose of this file is to be the input to a redesign. It therefore
spends more words on what does not work than on what does.

---

## 1. What the thing is

A static Astro site, `securesein.github.io`. A Python pipeline in GitHub
Actions turns feeds into two kinds of output:

- **structured data** — JSON records committed to the repo and rendered
  as tables;
- **short posts** — markdown in `src/content/blog/`.

There is no database and no server. Every piece of state is a file in
git, which is also the audit trail: you can `git log` any number the
site has ever shown.

Reader-facing surfaces: `/model-updates`, `/research`, `/security`,
`/benchmarks` (a measurements table with roundup posts beneath it),
`/fundamentals` (hand-written explainers), `/topics`, `/threads`,
`/search`.

### Current totals

| | |
|---|---|
| Posts | 54 |
| Benchmark measurements | 1355 |
| Models in the closed registry | 250 |
| Radar files | 2 |
| Workflows | 11 |

Posts by kind: research 25, security 13, release 9, explainer 5,
benchmark 2.

---

## 2. Operational state, right now

| Channel | Workflow | GitHub | External trigger | Publishing? |
|---|---|---|---|---|
| Model Updates | `releases.yml` | **active** | every 6h | nothing since the ledger began |
| Benchmarks | `benchmarks.yml` | **active** | daily 06:00 | 2 roundups |
| Research | `research.yml` | disabled | *(cron job to be deleted)* | retired |
| Security | `security.yml` | disabled | *(cron job to be deleted)* | retired |
| AI news pipeline | `nieuwsbrief.yml` | disabled | *(cron job to be deleted)* | retired |
| Reader — papers | `papers.yml` | disabled | *(cron job to be deleted)* | retired prototype |
| Reader — raw feed | `raw_research_feed.yml` | disabled | *(cron job to be deleted)* | retired prototype |
| Daily digest | `digest.yml` | active | daily 18:00 | Telegram only, no AI cost |
| Feedback receiver | `feedback.yml` | active | every 5 min | Telegram only, no AI cost |
| Weekly report | `weekly-report.yml` | active | every 4h | Telegram only, no AI cost |
| Deploy | `deploy.yml` | active | triggered by the others | — |

The decision taken: **only Model Updates and Benchmarks remain as
content channels**, and both must run fully automatically and cheaply.

### What has actually been published

`state/ledger.json` holds 15 entries, 2026-09-17 to 2026-10-03:

| Channel | Posts |
|---|---|
| research | 7 |
| security | 6 |
| benchmarks | 2 |
| **releases** | **0** |

The 9 posts with `kind: "release"` on the site all date from 29 August
to 11 September and come from the *previous* pipeline, before this
architecture. **The Model Updates channel in its current form has never
published anything.** Section 9.1 explains why.

---

## 3. How a channel works

Two of the five channels share one flow (`core/pipeline.py`); the
Benchmarks channel does not and is described separately in §5.

```
feeds
  -> ingestion          per-source adapters, each failure-isolated
  -> deduplication      url -> title -> entity (3 layers, cost order)
  -> exclusion filter   interest_profile exclude[] — a hard drop
  -> classification     section / format / topics, closed enums
  -> quality gate       pass/fail against a threshold
  -> relevance ranking  orders the queue, never opens it
  -> budget check
  -> publish top N  |  everything else to the Radar
  -> verification gates
  -> commit
```

Three principles are enforced in code, not asked of a prompt, and they
are the strongest part of the design:

1. **Tiering.** A source is `primary`, `corroborating` or `community`.
   Only `primary` may trigger a post. Checked in code.
2. **Closed vocabularies.** Models, benchmarks, sections, formats and
   topics all resolve against registry files. An unresolved name is
   parked in `state/unresolved_models.jsonl` for a human and **never
   auto-registered**. This is what stopped `FINAL-Bench/Darwin-180B-RSI`
   — an unknown org self-reporting 94.44% on GPQA — from entering the
   benchmark table.
3. **Gates after drafting.** A draft that fails one is rejected and
   logged; there is no retry and no override.

| Gate | Checks | Cost |
|---|---|---|
| G1 | every number in the draft appears in the source text | free |
| G2 | the entity the post is about is named in the source | free |
| G3 | an LLM verifier reads draft against source | one call |
| G4 | the content schema, via `astro build` in CI | free |
| G5 | every figure traces to a cited measurement (roundups) | free |

Gate order is cost order: the free deterministic checks run before the
paid one, so a draft with an invented number never costs anything to
reject.

---

## 4. Model Updates (`releases.yml` + `channels/releases.py`)

Answers "what is new in the model landscape". 834 lines, the largest
channel.

```
ingest -> age filter (14 days) -> seen-cursor
       -> LLM classifies the event type and extracts the model
       -> score against a weights table
       -> threshold 6.0 -> max 2 posts/run, 10-day cooldown per model
```

**Sources** — `feeds-releases.json`, 44 entries: vendor news and API
changelogs (OpenAI, Anthropic, Google, xAI, Microsoft, AWS, Mistral),
~18 Hugging Face org endpoints for labs with no usable RSS (Qwen,
DeepSeek, Moonshot, Z.ai, MiniMax, ByteDance, Tencent, Baidu, Meta,
NVIDIA, IBM, Ai2, Liquid, Reka, Cohere), and corroborating serving-stack
feeds (vLLM, llama.cpp, Ollama, Transformers, SGLang).

**Scoring** (`config/releases.json`, threshold 6):

```
primary_source            +3     open_weights             +2
event_new_model           +4     tier1_vendor             +1
event_version_bump_major  +3     non_tier1                -2  (unknown labs only)
event_version_bump_minor  +1     benchmark_claims_present +1
event_capability_update   +2     corroborated_48h         +1
event_deprecation         +2     press_release_only       -3
event_availability        +1     entity_in_cooldown       -5
```

Vendors sit in three tiers: `tier1_vendors` (+1), `watched_vendors` (0 —
labs we track on purpose), everything else (-2).

---

## 5. Benchmarks (`benchmarks.yml` + `channels/benchmarks.py`)

Does **not** use the shared flow. 249 lines.

```
adapters -> normalise to the collection schema
         -> resolve the model name against models.json (closed)
         -> upsert measurements        <- this is the channel; free
         -> evaluate post triggers
         -> draft one roundup if fired triggers total >= 4
```

Committing measurements consumes no post budget and **no model call**.
Most days produce data and no post, and that is the designed outcome.
Only a roundup costs anything.

**Adapters** (`core/adapters/`), two of them:

| Adapter | Source | Produces |
|---|---|---|
| `epoch` | Epoch AI benchmark bundle, CC-BY | 1263 independent measurements |
| `hf_leaderboard` | Hugging Face Community Evals | 30 vendor-claimed measurements |

`measuredBy` is `vendor`, `thirdparty` or `community`, and the
`/benchmarks` table shows all three in one table distinguished by a
badge. Showing a vendor's claim beside an independent measurement of the
same model is the page's entire reason to exist.

**Triggers** (`config/benchmarks.json`, threshold 4, max 2 roundups/week):

```
benchmark_erratum_or_retraction  5
new_leader                       4   <- vendor claims are excluded from this
vendor_vs_thirdparty_gap         4
new_top5_entrant                 2
first_measurement_of_tier1_model 2
```

Coverage: 9 of 12 tracked benchmarks have data (frontiermath 337,
terminal-bench 326, gpqa-diamond 312, arc-agi-2 173, aider-polyglot 53,
hle 48, swe-bench-verified 35, livebench 21, osworld 20). **MMLU-Pro,
LMArena Text Elo and LiveCodeBench have no adapter and therefore no
rows.**

---

## 6. Cost control

This exists because of a real incident on 2026-09-21 — a run made 438
model calls, and no budget then in force counted money or counted the
calls that happen *before* drafting.

`core/spend.py` is a circuit breaker enforced inside the LLM wrapper
itself, not in the pipeline, "because LLM is the one place every paid
call has to pass through".

| Ceiling | Value |
|---|---|
| Model calls per run | 150 |
| Spend per run | $0.15 |
| Spend per day | $0.75 |
| Spend per rolling 7 days | $3.00 |
| Spend per rolling 30 days | $10.00 |

It is deliberately biased towards stopping: an unpriced model is charged
at the most expensive known rate, a response with no usage data is
charged a pessimistic estimate, and an unreadable spend file refuses the
run rather than assuming a clean slate.

Post budgets (`config/budgets.json`) are separate and count posts, not
money: hard cap 50 per rolling 7 days, 5 per day, 2 per run, and per
section per 7 days — release 6, research 6, security 4, benchmark 2,
explainer 1.

**Measured reality:** the whole of the last 30 days cost about **$0.35**.
A Benchmarks run with no new data costs **$0.00**; one that writes a
roundup costs about **$0.005**. A Model Updates run costs about
**$0.001–0.010** depending on how many items are new. The ceilings are
nowhere near being approached — the system's problem has never been
spending too much, it has been spending a little and producing nothing.

---

## 7. Scheduling — and a contradiction worth fixing

**Every channel workflow carries this comment:**

> `MANUAL TRIGGER ONLY. THERE IS DELIBERATELY NO schedule.`
> *It defaults to a DRY RUN. The `publish` input has to be set to true
> by hand, per run, for anything to be written.*

**And every one of them is nevertheless fired automatically**, by jobs
in a **cron-job.org** account that POST to the GitHub API's
`workflow_dispatch` endpoint with `publish: true`. That account is
outside this repository and outside any agent's reach.

This arrangement exists because GitHub's own `schedule:` trigger was
measured at roughly a 10% fire rate on this repo, against ~100% for
`workflow_dispatch`. The external trigger was the fix. But it means:

- the code's stated intent and its actual operation disagree, and a
  reader of the repo cannot see the real cadence anywhere in it;
- when the workflows were disabled for two days, every dispatch failed,
  and **cron-job.org silently auto-disabled the hourly Model Updates job**.
  Nothing in the repo noticed or reported this. It was found by watching
  a clock.

Any redesign should decide deliberately where the schedule lives, and
make the system able to notice its own silence.

---

## 8. State and data model

Everything authoritative is a file.

| File | Role |
|---|---|
| `models.json` | 250-model closed registry; vendor, family, aliases, release date |
| `benchmarks.json` | 12 tracked benchmarks; metric, unit, direction |
| `taxonomy.json` | sections, formats, topics — the closed IA vocabulary |
| `categories.json` | topic taxonomy shared by Astro and Python |
| `feeds*.json` | source lists per channel |
| `config/*.json` | thresholds, weights, budgets — **all policy lives here** |
| `state/ledger.json` | what was published, when, by which channel |
| `state/spend.json` | every run's model calls and dollars |
| `state/queue.json` | candidates above threshold with no budget yet |
| `state/rejected.jsonl` | every rejection with its reason — 5416 lines, the single most useful diagnostic in the system |
| `state/seen_*.json` | per-channel cursor of item ids already looked at |
| `state/entities.json` | per-model publication cooldown |
| `state/unresolved_models.jsonl` | names parked for a human |
| `src/content/benchmarks/*.json` | one file per measurement; the filename is its id |

The design rule for thresholds is good and should survive: *change a
number in a config file, never reword a prompt — a prompt change is
unmeasurable and a threshold change is not.*

---

## 9. What is structurally wrong

This is the section that matters for a redesign. Each item has evidence.

### 9.1 Free-text model output meets closed vocabularies, with nothing in between

The classifier prompt asks for a vendor; the model answers `"OpenAI"`;
`config/releases.json` holds `"openai"`. Nothing normalised between
them, so `vendor in tier1_vendors` was false for **every** live-classified
item and the rubric charged `non_tier1 (-2)` instead of
`tier1_vendor (+1)` — on OpenAI's and Anthropic's own announcements:

```
Introducing GPT-6 Sol and Luna   5.0  primary +3, new_model +4, non_tier1 -2
We've launched Claude Sonnet 5.5 3.0  primary +3, minor +1, non_tier1 -2, corroborated +1
Kimi K3 GA on Amazon Bedrock     4.0  primary +3, availability +1, open_weights +2, non_tier1 -2
```

Against a threshold of 6. **This is why the channel never published.**
Fixed 2026-10-03, but the *class* of bug is the lesson: the codebase
enforces `eventType` and `modality` against their enums in code and
forgot to do it for `vendor`. A redesign should make that enforcement
structural rather than per-field.

A second instance of the same class: `is_major()` treated "6.1" as a
point release, so `GPT-6.1 Sol` scored 5.0. Labs ship 6.1, 5.5 and 4.7
as new models. Also fixed.

### 9.2 Detection source and narration source are not the same thing

Hugging Face Hub API endpoints are the best *detector* in the system — a
first-party, timestamped signal from labs with no usable RSS. They are a
useless *describer*: a model repo page has no prose saying what changed
or where to run it.

Result: **115 of 115** `no_product_angle` rejections came from
`huggingface.co`, each after an expensive drafting call. A dry run on
2026-10-03 produced three candidates above threshold — `nvidia/PixelUMM`,
`nvidia/PixelDiT2-ImageNet`, `RekaAI/Reka-Inverse-Dynamics-Model` — and
all three died the same way.

The model card README *is* fetchable (`/raw/main/README.md`, HTTP 200,
3–5 KB of real prose). Nothing uses it. A redesign should separate "what
tells me this happened" from "what do I write from".

### 9.3 Config that nothing reads

`feeds-benchmarks.json` holds ~20 carefully researched sources with
licences and notes. `FEEDS_BENCHMARKS_FILE` is defined in
`core/constants.py` and **imported nowhere**. The Benchmarks channel has
a hardcoded `ADAPTERS` dict. Adding an entry to that file changes
nothing at runtime; each source needs a Python adapter.

Research delivered as config, that cannot become behaviour, is a trap
for whoever reads it next.

### 9.4 The seen-cursor is irreversible, and loss is silent

An item marked seen never returns. Every real release the vendor bug
dropped — GPT-6.1 Sol, Claude Sonnet 5.5, Claude Opus 5.5, Grok 4.7 — is
in `state/seen_releases.json` and **will not be reconsidered**. The fix
works forwards only. There is no replay path and no way to ask "what
would this have done last month".

### 9.5 Work was spent on items that could never produce anything

Corroborating sources were sent to the LLM classifier *before* the
tier check, even though `attach_corroboration()` reads only an item's
title, summary, source and date and never its facts.
`ggml-org/llama.cpp` alone — roughly ten builds a day, a corroborating
source that can never trigger anything — spent **265 model calls** being
told it was `not_a_release`: 64% of every such rejection logged. Fixed
2026-10-03 by moving one check above another.

### 9.6 The circuit breaker and CI disagreed about what a failure is

The spend ceiling exits non-zero on purpose, as an incident to look at.
The workflow's later steps ran only on success, so the commit step was
skipped and the `seen` cursor was never pushed. Research and Security
therefore re-fetched the identical ~300-item backlog every four hours,
hit the identical ceiling, and aborted again — **three days, a few cents
each time, zero forward progress**, and nothing reported it. Fixed, but
the shape of the failure is worth remembering: a safety mechanism that
is correct in isolation and wrong in its environment.

### 9.7 Derived numbers cannot survive G5

A trigger stated "a 14.7 point gap". That text is pasted into the
roundup prompt verbatim, the prompt tells the model to reuse those
numbers exactly, and G5 then rejects any figure that is not the value of
a cited measurement. 14.7 is a subtraction, so every draft was
guaranteed to be discarded. Fixed by stating the comparison in words.

### 9.8 One model has many measurements, and comparisons must know it

Epoch runs one model at several reasoning efforts and stores each as its
own record: `glm-5-2` on GPQA is 91.86 at max effort, 87.88 at low,
71.21 at none. The gap trigger compared a vendor claim against each in
turn and fired on the weakest, reporting "a 20.0 point gap" for a vendor
whose claim matched the max-effort run to within 0.7. That would have
published a false accusation against a named company on the channel's
first run with vendor data. Now compared against the *range*. Conditions
are part of a measurement's identity everywhere else in the system; this
was the one place that forgot.

### 9.9 Budgets describe a system that does not exist

`targets_7d` allows 16 posts a week across the sections. Actual output
over the last 30 days: **3 posts**. The budget is not the constraint and
has never been the constraint, which means tuning it is not a lever.

### 9.10 Volume mismatch on the retired channels

Research and Security pulled from 62 + 23 sources with one LLM call per
item for classification and quality gating. A run saw 300+ new items and
a 150-call ceiling. They were structurally unable to finish a run. If
anything like them returns, the per-item-LLM-call shape is the thing to
redesign, not the ceiling.

---

## 10. Constraints any new design must respect

- **The spend ceilings are not negotiable.** They exist because of a
  real incident and they are the reason a bug costs cents rather than
  hundreds.
- **No database, no service.** Files in git, because the audit trail is
  the product.
- **Closed vocabularies, never auto-populated.** This is what keeps
  self-published nonsense out of the tables.
- **Gates are not re-rollable.** "A gate you can re-roll is not a gate."
- **Policy in config, not in prompts.** A threshold is measurable; a
  reworded prompt is not.
- **It runs unattended.** A broken adapter must be data, not an exit
  code — but something must then say so out loud, which today it does
  not.
- **No paid API keys beyond OpenAI.** Tokenless public endpoints
  preferred.
- **Licences are honoured.** Epoch is CC-BY and the attribution is
  rendered on the page.

---

## 11. Questions a redesign should answer

1. **What is a channel, actually?** Benchmarks (data first, prose
   occasionally, $0 most days) and Model Updates (prose first, one LLM
   call per candidate) share almost nothing but a folder. Is the shared
   pipeline earning its place?
2. **Where does the schedule live**, and how does the system notice when
   it has gone quiet? Today, silence and health look identical.
3. **Should detection and narration be separated** — a cheap structured
   detector, and a describer that only runs on something worth
   describing, from a source chosen because it has prose?
4. **Is per-item LLM classification affordable at any useful feed
   volume**, or should classification be deterministic with the model
   reserved for writing?
5. **What replaces the seen-cursor** so that a bug fixed today can be
   replayed against last month?
6. **Does the `/benchmarks` table want more vendor claims** — the only
   trigger that has ever produced an interesting post came from the
   vendor-vs-independent contrast, and only 30 of 1355 records are
   vendor claims.
7. **Three benchmarks have no adapter.** Drop them from the tracked
   list, or build them?
