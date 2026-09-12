export const SITE = {
  title: "securesein",
  description:
    "Applied AI, taken apart — the news as it breaks, the fundamentals that stay true, and deep dives into the papers and systems behind it. Curated by a human, drafted in part by an AI.",
  tagline: "Applied AI, taken apart.",
  subTagline: "Curated by a human, drafted in part by an AI.",
  author: "Sebastiaan",
  authorRole: "IT consultant",
  github: "",
};

// The three lanes, in nav order — fastest and shallowest first. These
// are the `kind` axis from /taxonomy.json (how a post was made and how
// long it takes), deliberately not mixed with the `topics` axis (what
// it is about), which has its own directory at /topics/. Mixing the
// two into one flat pill list is what the old nav did.
export const SECTIONS = [
  {
    kind: "news" as const,
    label: "News",
    href: "/news",
    description: "Drafted automatically from the source, minutes old.",
  },
  {
    kind: "explainer" as const,
    label: "Fundamentals",
    href: "/fundamentals",
    description: "One concept at a time, still true next year.",
  },
  {
    kind: "deepdive" as const,
    label: "Deep dives",
    href: "/deep-dives",
    description: "One paper or system, taken apart properly.",
  },
];

export const NAV_LINKS = [
  { label: "Topics", href: "/topics" },
  { label: "About", href: "/about" },
];
