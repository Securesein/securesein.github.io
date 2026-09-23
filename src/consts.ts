import { SECTION_INFO, SECTION_ORDER } from "./taxonomy";

export const SITE = {
  title: "securesein",
  description:
    "Machine learning, kept up with and taken apart — what shipped, what we learned, what the numbers say, and what can go wrong. Drafted automatically, published without review, with the reason on every post.",
  // The homepage <title> specifically. Every other page gets
  // "<page> — securesein" from its own title, but the homepage had no
  // title of its own and fell back to the bare brand name — the single
  // most valuable title tag on the site, carrying not one word about
  // what the site is. Nobody searches "securesein" except people who
  // already know it. Kept under ~60 characters so it isn't truncated
  // in results.
  homeTitle: "securesein — AI research, model updates and benchmarks",
  tagline: "securesein",
  subTagline: "Keeping up with machine learning, one mechanism at a time.",
  author: "Sebastiaan",
  // Rendered into every post's JSON-LD as the author's jobTitle, which
  // is why it has to match what the About page says rather than being
  // a leftover from an earlier framing of the site.
  authorRole: "Machine learning writer",
  github: "https://github.com/Securesein/securesein.github.io",
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

/**
 * Which background the homepage hero draws. Both live in index.astro's
 * stylesheet behind a `[data-hero-bg]` attribute, so switching between
 * them — or back — is this one value and nothing else.
 *
 *   "topo" — the static warped contour lines (the previous default).
 *   "dots" — a dot matrix with one slow sheen sweeping across it.
 *
 * Only one of the two is ever rendered; the other's rules simply don't
 * match. Keep it at one moving element per page (dotmatrix handoff C1):
 * if "dots" is active, the sweep is the homepage's whole motion budget.
 */
export const HERO_BACKGROUND: "topo" | "dots" = "dots";

export const NAV_LINKS = [
  { label: "Topics", href: "/topics" },
  { label: "About", href: "/about" },
];
