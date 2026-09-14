// Canonical taxonomy for the site — the actual data lives in
// /taxonomy.json at the repo root (not under src/) so the Python
// pipeline can read the exact same file when it asks the model to pick
// a section, a format and topics, without a second, driftable copy.
//
// Three orthogonal axes (brief §3.1), deliberately not one list:
//   section — why would someone read this? Exactly 1 per post, stored
//             in frontmatter as `kind` (the field name predates the
//             axis name and post URLs depend on nothing here, so it was
//             not worth a rename).
//   format  — what shape is this piece? Exactly 1 per post.
//   topics  — what is it technically about? 1-3 per post, closed
//             vocabulary.
//
// Nothing in this file enumerates a slug by hand. The `Section`,
// `Format` and `Topic` types are derived from the JSON keys, so adding
// a section to taxonomy.json is a one-file change and removing one is
// a type error everywhere it was still referenced.
import raw from "../taxonomy.json";

export interface SectionInfo {
  label: string;
  href: string;
  plural: string;
  /** The one-line question this section answers (brief §3.2). */
  question: string;
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
  sections: Record<string, SectionInfo>;
  formats: Record<string, FormatInfo>;
  topics: Record<string, TopicInfo>;
};

export const SECTION_INFO = data.sections;
export const FORMATS = data.formats;
export const TOPICS = data.topics;

/**
 * `kind` is the frontmatter field that carries the section. KINDS is
 * kept as the name components use, because that is what the field is
 * called on a post; SECTION_INFO is the same object under the axis
 * name the brief uses.
 */
export const KINDS = SECTION_INFO;

export const SECTION_SLUGS = Object.keys(SECTION_INFO) as [string, ...string[]];
export const KIND_SLUGS = SECTION_SLUGS;
export const FORMAT_SLUGS = Object.keys(FORMATS) as [string, ...string[]];
export const TOPIC_SLUGS = Object.keys(TOPICS) as [string, ...string[]];

export type Section = keyof typeof data.sections & string;
/** Alias: the frontmatter field is `kind`, the axis is "section". */
export type Kind = Section;
export type Format = keyof typeof data.formats & string;
export type Topic = keyof typeof data.topics & string;
export type Credit = "scout" | "directed" | "written";

/**
 * Nav and listing order for the five sections. Declared here rather
 * than taken from Object.keys so a reordering is a deliberate edit and
 * not a side effect of how the JSON happens to be written — but it is
 * still derived from the vocabulary, so a section that exists and is
 * missing here would be caught by the check below.
 */
export const SECTION_ORDER: Section[] = [
  "release",
  "research",
  "benchmark",
  "security",
  "explainer",
];
export const KIND_ORDER = SECTION_ORDER;

/**
 * Topic pages group by section, best-material-first: the sections that
 * take a subject apart come before the ones that report on it.
 */
export const SECTION_ORDER_BY_DEPTH: Section[] = [
  "explainer",
  "research",
  "benchmark",
  "security",
  "release",
];
export const KIND_ORDER_BY_DEPTH = SECTION_ORDER_BY_DEPTH;

// A section present in taxonomy.json but missing from the two order
// lists would silently vanish from the nav and from topic pages. Fail
// the build instead.
for (const slug of SECTION_SLUGS) {
  if (!SECTION_ORDER.includes(slug) || !SECTION_ORDER_BY_DEPTH.includes(slug)) {
    throw new Error(
      `taxonomy.json defines section "${slug}" but src/taxonomy.ts does not ` +
        `place it in SECTION_ORDER / SECTION_ORDER_BY_DEPTH.`
    );
  }
}

/** URL segment for a format, e.g. `deepdive` -> `deep-dive`. */
export function formatSlug(format: Format): string {
  return FORMATS[format].slug;
}

/** Inverse of formatSlug. */
export function formatFromSlug(slug: string): Format | undefined {
  const entry = Object.entries(FORMATS).find(([, info]) => info.slug === slug);
  return entry?.[0] as Format | undefined;
}

/** Route for a section, read from the vocabulary rather than typed out. */
export function sectionHref(section: Section): string {
  return SECTION_INFO[section].href;
}
