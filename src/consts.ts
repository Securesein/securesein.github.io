export const SITE = {
  title: "securesein",
  description:
    "Notes on applied AI, enterprise mobility, and the Microsoft ecosystem — curated by a human, drafted by an AI.",
  author: "Sebastiaan",
  authorRole: "IT consultant",
  github: "",
};

// The two content sections, shown together in the header's dropdown
// (see SectionNav.astro) — kept as one explicit choice instead of two
// separate flat nav links, since "Blog" alone read as the only path
// and left "News" only implicit.
export const SECTIONS = [
  {
    label: "News",
    href: "/blog",
    description: "Timely AI news, auto-summarized from RSS.",
  },
  {
    label: "AI Fundamentals",
    href: "/fundamentals",
    description: "Evergreen explainers, hand-curated.",
  },
];

export const NAV_LINKS = [{ label: "About", href: "/about" }];
