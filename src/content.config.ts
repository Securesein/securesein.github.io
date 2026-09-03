import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
import { CATEGORY_SLUGS } from "./categories";

const blog = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/blog" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    // Must be one of CATEGORY_SLUGS (src/categories.ts) — keep tags to that
    // fixed taxonomy instead of free-form strings.
    tags: z.array(z.enum(CATEGORY_SLUGS as [string, ...string[]])).default([]),
    draft: z.boolean().default(false),
    sourceUrl: z.string().url().optional(),
    sourceName: z.string().optional(),
    // Who wrote this post — see src/authors.ts. Defaults to "ai" because
    // that's what the pipeline writes; "sebastiaan" is for occasional
    // hand-written posts.
    author: z.enum(["ai", "sebastiaan"]).default("ai"),
  }),
});

export const collections = { blog };
