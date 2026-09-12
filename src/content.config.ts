import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
import { KIND_SLUGS, FORMAT_SLUGS, TOPIC_SLUGS } from "./taxonomy";

// Posts published before this date were written under the old
// two-field (`section` + `tags`) model, when Scout didn't record its
// source in a structured field. The `source`-is-required rule is a
// hard build error from this date onward and a non-blocking warning
// before it — see scripts/check_content_warnings.mjs, which reports
// the stragglers without failing the build. Everything Scout writes
// from now on carries a source, so this only ever covers the archive.
export const SCHEMA_CUTOVER = new Date("2026-09-12T00:00:00Z");

const blog = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/blog" }),
  schema: z
    .object({
      title: z.string(),
      description: z.string(),
      pubDate: z.coerce.date(),
      updatedDate: z.coerce.date().optional(),

      // Axis 1 — how it was made and how long it takes. Exactly one per
      // post; decides the section landing page, the card shape and the
      // breadcrumb. See src/taxonomy.ts.
      kind: z.enum(KIND_SLUGS),
      // Sub-shape of a deep dive, rendered as filter chips on
      // /deep-dives/. Only meaningful when kind === "deepdive".
      format: z.enum(FORMAT_SLUGS).optional(),
      // Axis 2 — what it is about. Closed vocabulary on purpose: an
      // open one rots within a month once the pipeline starts
      // inventing slugs.
      topics: z.array(z.enum(TOPIC_SLUGS)).min(1).max(3),

      // Authorship — deliberately not a binary. A model drafts nearly
      // all the prose on this site, including Fundamentals and Deep
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
    })
    .refine((d) => d.kind !== "deepdive" || d.format !== undefined, {
      message: "deepdive posts need a format",
      path: ["format"],
    })
    .refine((d) => d.kind === "deepdive" || d.format === undefined, {
      message: "format only applies to deepdive posts",
      path: ["format"],
    })
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
    }),
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

export const collections = { blog, threads };
