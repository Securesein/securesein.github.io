// Canonical category taxonomy for blog posts.
//
// This is the fixed list the pipeline should classify every post into
// (one or two categories per post, not more). Keeping it fixed instead of
// letting the LLM invent free-form tags keeps the blog index and post
// pages consistent over time.
export const CATEGORIES = {
  models: {
    label: "Models",
    description: "New model releases, capability updates, benchmarks.",
  },
  "agents-tooling": {
    label: "Agents & Tooling",
    description: "Agentic workflows, dev tools, frameworks, APIs.",
  },
  "safety-alignment": {
    label: "Safety & Alignment",
    description: "Safety research, red-teaming, alignment, evals.",
  },
  research: {
    label: "Research",
    description: "Papers and technical research that don't fit elsewhere.",
  },
  "policy-regulation": {
    label: "Policy & Regulation",
    description: "AI law, governance, standards, government action.",
  },
  "industry-business": {
    label: "Industry & Business",
    description: "Funding, partnerships, market moves, company news.",
  },
  "enterprise-microsoft": {
    label: "Enterprise & Microsoft",
    description: "EMM, Intune, Microsoft 365 and enterprise IT topics.",
  },
  meta: {
    label: "Meta",
    description: "Site announcements and personal notes about this blog.",
  },
} as const;

export const CATEGORY_SLUGS = Object.keys(CATEGORIES) as Array<
  keyof typeof CATEGORIES
>;
