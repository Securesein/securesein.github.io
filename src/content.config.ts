import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
import { KIND_SLUGS, FORMAT_SLUGS, TOPIC_SLUGS } from "./taxonomy";
import { BENCHMARK_SLUGS } from "./registries";

// Two cutovers, because the archive was written under two different
// contracts and collapsing them into one date would either fail the
// build on posts that were correct when written or soften a rule that
// must be hard for everything published from here on.
//
// SCHEMA_CUTOVER — the IA redesign. Posts before it used a two-field
// (`section` + `tags`) model and did not record a structured `source`.
// The `source`-is-required rule is a hard build error from this date
// onward and a non-blocking warning before it (see
// scripts/check_content_warnings.mjs, which reports the stragglers
// without failing the build).
export const SCHEMA_CUTOVER = new Date("2026-09-12T00:00:00Z");

// AUTONOMY_CUTOVER — the autonomous-publishing contract. The `release`
// block and the `scout` scoring block are both introduced by it and
// neither existed before, so no archive post can carry one honestly:
// back-filling an `eventType` or a `qualityScore` for a post written
// before those concepts existed would be fabricating exactly the
// structured facts these fields exist to make checkable. Every post
// from this date on must carry them.
//
// This is meant to be the date the pipeline is actually switched on —
// i.e. the day this branch is merged to main — not the day it was
// built. It was originally set to the build date (2026-09-14) as a
// placeholder; merging landed a day later (2026-09-15), and one real
// Scout post drafted by the pre-migration pipeline on the 14th got
// caught on the wrong side of that placeholder, which would have
// forced fabricating a `scout` score for a post the new pipeline never
// touched. Corrected once, here, to the actual switch-on day. Do not
// move it again after this: doing so on an ongoing basis is exactly
// the "quietly widen the exemption" failure mode this cutover exists
// to prevent.
export const AUTONOMY_CUTOVER = new Date("2026-09-15T00:00:00Z");

const blog = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/blog" }),
  schema: z
    .object({
      title: z.string(),
      description: z.string(),
      pubDate: z.coerce.date(),
      updatedDate: z.coerce.date().optional(),

      // Axis 1 — SECTION. Why would someone read this? Exactly one per
      // post; decides the landing page, the card shape and the
      // breadcrumb. The field is called `kind` for historical reasons;
      // the vocabulary is the section table in /taxonomy.json.
      kind: z.enum(KIND_SLUGS),
      // Axis 2 — FORMAT. What shape is this piece? Now required on
      // every post rather than being a deep-dive-only sub-shape: under
      // the three-axis model `news` and `deepdive` are formats, not
      // sections, so every post has one.
      format: z.enum(FORMAT_SLUGS),
      // Axis 3 — TOPICS. What is it technically about? Closed
      // vocabulary on purpose: an open one rots within a month once the
      // pipeline starts inventing slugs.
      topics: z.array(z.enum(TOPIC_SLUGS)).min(1).max(3),

      // Authorship — deliberately not a binary. A model drafts nearly
      // all the prose on this site, including Fundamentals and deep
      // dives; what separates the lanes is how much human judgement
      // went in. See src/credit.ts for how these render.
      credit: z.enum(["scout", "directed", "written"]),
      // What the human actually did. The disclosure sentence is
      // generated from these facts rather than hand-written per post,
      // because hand-written disclosure drifts into flattery.
      contributions: z
        .object({
          chose: z.boolean().default(false), // picked the subject and the angle
          checked: z.boolean().default(false), // verified claims against sources
          rewrote: z.boolean().default(false), // edited or rewrote passages
          built: z.boolean().default(false), // ran the experiment being described
        })
        .optional(),
      // The model that drafted it, named exactly. "An AI" is evasive.
      model: z.string().optional(),
      source: z
        .object({
          url: z.string().url(),
          publisher: z.string(),
          publishedAt: z.coerce.date().optional(),
        })
        .optional(),

      // Plain path under /public/images/<slug>/ rather than an
      // astro:content image() field — the existing archive already
      // references these files from markdown bodies by public path,
      // and moving them into src/ buys nothing here.
      hero: z.string().optional(),
      heroAlt: z.string().optional(),
      // Slugs from the `threads` collection this post is a part of.
      threads: z.array(z.string()).default([]),
      // Position in the Fundamentals reading path. Lower reads first;
      // anything without one falls to the end in publication order.
      // Recency is the wrong sort for evergreen explainers.
      order: z.number().optional(),
      // Set on a post that is superseded by a better one elsewhere on
      // the site — renders a cross-link instead of leaving the reader
      // on the weaker piece.
      betterCoveredBy: z.string().optional(),
      draft: z.boolean().default(false),

      // --- Model Updates only (brief §4) ------------------------
      // Structured facts about what shipped, so the entity-dedup key
      // (vendor, family, version, eventType) is read off the post
      // rather than re-derived from its prose. `vendor` and `family`
      // are canonical ids from /models.json.
      release: z
        .object({
          vendor: z.string(),
          family: z.string(),
          version: z.string().optional(),
          eventType: z.enum([
            "new_model",
            "version_bump",
            "availability", // GA, new region, pricing, new provider
            "deprecation",
            "capability_update", // new modality/context/tool support
          ]),
          openWeights: z.boolean().default(false),
          modality: z
            .array(z.enum(["text", "vision", "audio", "video", "embedding"]))
            .default(["text"]),
        })
        .optional(),

      // --- Benchmarks and anything citing a measurement ----------
      // Ids in the `benchmarks` collection. Every number a benchmark
      // post states has to trace to one of these; a Research piece may
      // also cite measurements, which is why this is not restricted to
      // kind "benchmark". Referential integrity (§4.1 rule 4) is a
      // cross-collection check and is enforced hard in
      // scripts/check_content_warnings.mjs.
      benchmarkRefs: z.array(z.string()).default([]),

      // --- Scoring provenance (brief §4) -------------------------
      // Written by Scout, rendered nowhere by default. This is how a
      // mis-tuned profile becomes visible: `whyRelevant` is the first
      // thing to read when the wrong things start getting published.
      scout: z
        .object({
          qualityScore: z.number().min(0).max(100),
          relevanceScore: z.number().min(0).max(100),
          whyRelevant: z.string().max(300),
          candidateId: z.string(),
        })
        .optional(),
    })
    // Existing rules, unchanged ------------------------------------
    .refine(
      (d) =>
        d.credit !== "scout" ||
        d.source !== undefined ||
        d.pubDate < SCHEMA_CUTOVER,
      {
        message: "Scout posts must carry their source",
        path: ["source"],
      }
    )
    .refine((d) => d.credit === "scout" || d.contributions !== undefined, {
      message: "non-Scout posts must state what the human actually contributed",
      path: ["contributions"],
    })
    .refine((d) => !d.hero || !!d.heroAlt, {
      message: "hero image needs alt text",
      path: ["heroAlt"],
    })

    // --- §4.1 refinement 1 ---------------------------------------
    // A Model Updates post without its structured facts cannot be
    // entity-deduped, and one without a source is a claim with nothing
    // behind it. Both are the whole point of the section.
    //
    // SOFTENED BEFORE AUTONOMY_CUTOVER. The archive predates the
    // `release` block entirely; back-filling one would mean inventing an
    // `eventType` for a post written when the concept did not exist,
    // which is exactly the kind of fabrication §5.1 forbids for model
    // names. scripts/check_content_warnings.mjs lists the stragglers.
    .refine(
      (d) =>
        d.kind !== "release" ||
        d.release !== undefined ||
        d.pubDate < AUTONOMY_CUTOVER,
      {
        message: "Model Updates posts need a `release` block",
        path: ["release"],
      }
    )
    .refine(
      (d) =>
        d.kind !== "release" ||
        d.source !== undefined ||
        d.pubDate < SCHEMA_CUTOVER,
      {
        message:
          "Model Updates posts must carry the vendor announcement as their source",
        path: ["source"],
      }
    )
    // --- §4.1 refinement 2 ---------------------------------------
    .refine((d) => d.kind === "release" || d.release === undefined, {
      message: '`release` only applies to kind "release"',
      path: ["release"],
    })
    // --- §4.1 refinement 3 ---------------------------------------
    // A benchmark post that cites nothing is prose about numbers
    // rather than a reading of them.
    .refine((d) => d.kind !== "benchmark" || d.benchmarkRefs.length >= 1, {
      message: "Benchmarks posts must cite at least one measurement",
      path: ["benchmarkRefs"],
    })
    // --- §4.1 refinement 5 ---------------------------------------
    // An auto-published post must always carry the reason it was
    // published. SOFTENED BEFORE AUTONOMY_CUTOVER: the archive's Scout
    // posts were published before two-stage scoring existed and have no
    // scores to record. Inventing a qualityScore for them would make the
    // one field that exists to expose a mis-tuned profile into fiction.
    .refine(
      (d) =>
        d.credit !== "scout" ||
        d.scout !== undefined ||
        d.pubDate < AUTONOMY_CUTOVER,
      {
        message:
          "an auto-published post must carry the reason it was published",
        path: ["scout"],
      }
    )
    // --- §4.1 refinement 6, repurposed ---------------------------
    // The brief's rule 6 was `format: fieldnote` is only valid with
    // `kind: practice`. Decision A2 removed both, so the rule as
    // written has nothing left to constrain. It is repurposed to the
    // one remaining section/format coupling that carries the same
    // meaning: a benchmark-shaped piece belongs in the Benchmarks
    // section, not filed as a Research or Model Updates post that
    // happens to look like a leaderboard reading.
    .refine((d) => d.format !== "benchmark" || d.kind === "benchmark", {
      message: '`format: "benchmark"` is only valid with `kind: "benchmark"`',
      path: ["format"],
    }),
  // §4.1 rule 4 — every id in `benchmarkRefs` resolves to a real entry
  // in the `benchmarks` collection — is a *cross-collection* check,
  // which a per-entry Zod schema has no way to express. It is enforced
  // as a hard failure in scripts/check_content_warnings.mjs
  // (`npm run check:content`), which exits non-zero on an error.
});

// Curated storylines. Hand-written only — the whole value of a thread
// is that a human chose the order, so nothing auto-generates these.
const threads = defineCollection({
  loader: glob({ pattern: "**/*.json", base: "./src/content/threads" }),
  schema: z.object({
    title: z.string(),
    blurb: z.string(),
    // Post ids (filename without .md), in reading order.
    posts: z.array(z.string()).min(2),
  }),
});

// One benchmark measurement per file (brief §5) — data, not posts,
// which is why this sits beside `threads` rather than inside the blog
// collection. The entry id is the filename, and the filename is the
// measurement id: `<benchmark>--<model>--<evaluator>[--<effort>]--<date>`.
//
// `measuredBy` plus `conditions` is the reason this collection exists.
// A score without a harness and a shot count is a number, not a
// finding — so `measuredBy` has no default (a record must say who
// measured it, and "thirdparty" must never be assumed), and
// `conditions` is required and refined to be non-empty.
const benchmarks = defineCollection({
  loader: glob({ pattern: "**/*.json", base: "./src/content/benchmarks" }),
  schema: z
    .object({
      // Canonical ids from /models.json and /benchmarks.json. An
      // unresolved model never reaches this file: the pipeline parks it
      // in state/unresolved_models.jsonl instead.
      model: z.string(),
      vendor: z.string(),
      benchmark: z.enum(BENCHMARK_SLUGS),

      metric: z.enum([
        "accuracy",
        "elo",
        "pass@1",
        "resolved",
        "score",
        "cost_usd",
      ]),
      value: z.number(),
      unit: z.enum(["percent", "elo", "score", "usd", "seconds"]),

      measuredBy: z.enum(["vendor", "thirdparty", "community"]),
      evaluator: z.string(),
      harness: z.string().optional(),

      conditions: z.object({
        shots: z.number().optional(),
        tools: z.boolean().optional(),
        reasoningEffort: z.string().optional(),
        temperature: z.number().optional(),
        notes: z.string().optional(),
      }),

      measuredAt: z.coerce.date(),
      sourceUrl: z.string().url(),
      publisher: z.string(),
      // Attribution requirement of the source dataset, rendered next to
      // the table. Epoch AI's data is CC-BY and saying so is a licence
      // condition, not a courtesy.
      license: z.string().optional(),
      attribution: z.string().optional(),
      // Id of an earlier measurement this replaces — a re-run of the
      // same (benchmark, model, evaluator, conditions) with a new value.
      supersedes: z.string().optional(),
    })
    .refine(
      (d) =>
        d.conditions.shots !== undefined ||
        d.conditions.tools !== undefined ||
        d.conditions.reasoningEffort !== undefined ||
        d.conditions.temperature !== undefined ||
        !!d.conditions.notes?.trim(),
      {
        message:
          "a measurement with empty conditions is a number, not a finding",
        path: ["conditions"],
      }
    ),
});

// The Radar (brief §6) — everything that passed the quality gate and
// lost on ranking. One file per month, an array of records, so the
// file count stays sane at 30-50 items a day.
//
// DECISION A3: INTERNAL ONLY. There is deliberately no /radar/ route,
// no navigation entry, no RSS feed and no sitemap presence. The Radar
// exists as pipeline data and as Telegram digest input. It is a
// collection rather than a plain state/ file so the same Zod validation
// that guards posts guards it, and so a future decision to surface it
// is a route away rather than a migration.
const radar = defineCollection({
  loader: glob({ pattern: "**/*.json", base: "./src/content/radar" }),
  schema: z.object({
    month: z.string(), // "2026-09"
    items: z.array(
      z.object({
        id: z.string(),
        url: z.string().url(),
        title: z.string(),
        source: z.string(),
        section: z.enum(KIND_SLUGS),
        topics: z.array(z.enum(TOPIC_SLUGS)).max(3).default([]),
        qualityScore: z.number().min(0).max(100),
        relevanceScore: z.number().min(0).max(100),
        // One sentence. Not decoration: this is how a mis-tuned profile
        // becomes visible in the daily digest.
        whyRelevant: z.string().max(200),
        seenAt: z.coerce.date(),
        status: z.enum(["radar", "promoted", "dismissed"]).default("radar"),
        promotedTo: z.string().optional(), // post slug, once written up
        feedback: z
          .enum(["interesting", "not_useful", "not_my_topic", "deep_dive"])
          .optional(),
      })
    ),
  }),
});

export const collections = { blog, threads, benchmarks, radar };
