// Canonical taxonomy for the site — the actual data lives in
// /taxonomy.json at the repo root (not under src/) so the Python
// pipeline can read the exact same file when it asks the model to pick
// topics, without a second, driftable copy of the list. This replaces
// the older /categories.json, which mixed subject tags ("Models") with
// reading modes ("Research") in one flat list.
//
// Three separate axes, deliberately not one list (see the IA brief):
//   kind    — how it was made / how long it takes. Exactly 1 per post.
//   format  — sub-shape of a deep dive. Optional, deepdive only.
//   topics  — what it is about. 1-3 per post, closed vocabulary.
import raw from "../taxonomy.json";

export interface KindInfo {
  label: string;
  href: string;
  plural: string;
  blurb: string;
  description: string;
}
export interface FormatInfo {
  label: string;
  slug: string;
  description: string;
}
export interface TopicInfo {
  label: string;
  description: string;
  blurb: string;
}

const data = raw as {
  kinds: Record<string, KindInfo>;
  formats: Record<string, FormatInfo>;
  topics: Record<string, TopicInfo>;
};

export const KINDS = data.kinds;
export const FORMATS = data.formats;
export const TOPICS = data.topics;

export const KIND_SLUGS = Object.keys(KINDS) as [string, ...string[]];
export const FORMAT_SLUGS = Object.keys(FORMATS) as [string, ...string[]];
export const TOPIC_SLUGS = Object.keys(TOPICS) as [string, ...string[]];

export type Kind = "news" | "explainer" | "deepdive";
export type Format = "paper" | "teardown" | "postmortem" | "notebook";
export type Topic =
  | "models"
  | "agents"
  | "safety"
  | "enterprise"
  | "mobility"
  | "selfhosted"
  | "industry";
export type Credit = "scout" | "directed" | "written";

/** Nav order for the three lanes — fastest/shallowest first. */
export const KIND_ORDER: Kind[] = ["news", "explainer", "deepdive"];

/** Topic pages group by kind best-material-first (brief §5.5). */
export const KIND_ORDER_BY_DEPTH: Kind[] = ["deepdive", "explainer", "news"];

/** URL segment for a deep-dive format, e.g. `paper` -> `paper-trail`. */
export function formatSlug(format: Format): string {
  return FORMATS[format].slug;
}

/** Inverse of formatSlug — used by /deep-dives/<format>/ routing. */
export function formatFromSlug(slug: string): Format | undefined {
  const entry = Object.entries(FORMATS).find(([, info]) => info.slug === slug);
  return entry?.[0] as Format | undefined;
}
