// Canonical category taxonomy for blog posts — the actual data lives in
// /categories.json at the repo root (not under src/) so the Python
// pipeline can read the exact same file when it asks the LLM to pick a
// category, without a second, driftable copy of this list.
import raw from "../categories.json";

export const CATEGORIES = raw as Record<
  string,
  { label: string; description: string }
>;

export const CATEGORY_SLUGS = Object.keys(CATEGORIES);
