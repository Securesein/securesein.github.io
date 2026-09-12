// Authorship, as a gradient rather than a binary.
//
// This replaces the old src/authors.ts, which mapped a two-value
// `author` field ("ai" | "sebastiaan") onto a byline and implied a
// clean human/AI split that does not exist: a model drafts nearly all
// the prose on this site, including Fundamentals and Deep dives. What
// differs between the lanes is how much human judgement went in, which
// is what `credit` + `contributions` record.
//
// The disclosure sentence is *generated* from those facts rather than
// hand-written per post — hand-written disclosure drifts into flattery
// within a month, and a generated one can never claim a review step
// that didn't happen.
import { SITE } from "./consts";
import type { Credit } from "./taxonomy";

export interface Contributions {
  chose: boolean;
  checked: boolean;
  rewrote: boolean;
  built: boolean;
}

export interface CreditInfo {
  /** Byline as shown on the post page and in card meta lines. */
  byline: string;
  /** Short qualifier after the byline. Empty where none is honest. */
  qualifier: string;
  /** Compact form for card meta lines. */
  short: string;
  /** True when no human read the post before it published. */
  unreviewed: boolean;
}

export const CREDITS: Record<Credit, CreditInfo> = {
  scout: {
    byline: "Scout",
    qualifier: "AI, unreviewed",
    short: "Scout",
    unreviewed: true,
  },
  directed: {
    byline: `${SITE.author} with AI`,
    qualifier: "",
    short: `${SITE.author} with AI`,
    unreviewed: false,
  },
  written: {
    byline: SITE.author,
    qualifier: "",
    short: SITE.author,
    unreviewed: false,
  },
};

const DEFAULT_CONTRIBUTIONS: Contributions = {
  chose: false,
  checked: false,
  rewrote: false,
  built: false,
};

interface DisclosureInput {
  credit: Credit;
  contributions?: Partial<Contributions>;
  model?: string;
  source?: { publisher: string; publishedAt?: Date };
  pubDate: Date;
}

function shortDate(date: Date): string {
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Joins a list the way a person writes one: "a, b and c". */
function sentenceList(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? "";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * The "How this was made" sentence, built from what actually happened.
 *
 * Copy rules, applied here rather than trusted to an author:
 *  - name the model ("an AI" is evasive, "gpt-4o" is a fact)
 *  - lead with whichever party did the *first* thing
 *  - plain past-tense verbs only — picked, drafted, checked, rewrote, ran
 *  - never mention a step whose contribution flag is false
 *  - no percentages, no apology; this is a credit line, not a warning
 */
export function disclosure(post: DisclosureInput): string {
  const model = post.model?.trim();
  const modelName = model || "a language model";

  if (post.credit === "scout") {
    const from = post.source
      ? ` from ${post.source.publisher}, ${shortDate(post.source.publishedAt ?? post.pubDate)},`
      : "";
    const using = ` using ${modelName}`;
    return (
      `Drafted by Scout${from}${using}. ` +
      `Published automatically — nobody read this before you did.`
    );
  }

  const c: Contributions = { ...DEFAULT_CONTRIBUTIONS, ...post.contributions };
  const who = SITE.author;

  if (post.credit === "written") {
    const tail = c.built ? ` ${who} built and ran the thing it describes.` : "";
    return `${who} wrote this one himself, without a model drafting it.${tail}`;
  }

  // credit: directed — he did the first thing, so he leads the sentence.
  const opening = c.built
    ? `${who} built and ran this himself`
    : c.chose
      ? `${who} picked the subject and set the angle`
      : `${who} commissioned this one`;

  const drafting = c.built
    ? `the write-up was drafted by ${modelName} from his notes`
    : `${modelName} drafted it`;

  // Only steps that actually happened get a clause. A false flag
  // produces silence, never a hedge — the sentence must not imply a
  // review that didn't take place, and must not apologise for one that
  // didn't either.
  const after: string[] = [];
  if (c.checked) after.push("checked the claims against the source");
  if (c.rewrote) after.push("rewrote where it got it wrong");

  const clauses = [opening, drafting];
  if (after.length) clauses.push(`he ${sentenceList(after)}`);

  return `${clauses.join("; ")}.`;
}

/**
 * One-line summary of the same facts, for card meta lines. Kept
 * understated and never colour-coded — the moment disclosure looks
 * like a warning label, readers start treating undisclosed writing as
 * the trustworthy default.
 */
export function creditShort(credit: Credit): string {
  return CREDITS[credit].short;
}
