import { SECTION_INFO, SECTION_ORDER } from "./taxonomy";

export const SITE = {
  title: "securesein",
  description:
    "Applied AI, taken apart — what shipped, what we learned, what the numbers say, and what can go wrong. Drafted automatically, published without review, with the reason on every post.",
  tagline: "Applied AI, taken apart.",
  subTagline: "Curated by a human, drafted in part by an AI.",
  author: "Sebastiaan",
  authorRole: "IT consultant",
  github: "",
};

/**
 * The five sections, in nav order. Generated from /taxonomy.json rather
 * than typed out here: the vocabulary has exactly one home, and adding
 * or removing a section is a one-file edit (plus its route). Each entry
 * keeps the `kind` slug so a listing can style by section without a
 * second lookup.
 *
 * This is the `kind` axis — why someone would read a piece —
 * deliberately not mixed with the `topics` axis (what it is about),
 * which has its own directory at /topics/, or with the `format` axis
 * (what shape it is), which is rendered on cards and drives the two
 * legacy format listings at /news/ and /deep-dives/.
 */
export const SECTIONS = SECTION_ORDER.map((kind) => ({
  kind,
  label: SECTION_INFO[kind].label,
  href: SECTION_INFO[kind].href,
  description: SECTION_INFO[kind].question,
}));

export const NAV_LINKS = [
  { label: "Topics", href: "/topics" },
  { label: "About", href: "/about" },
];
