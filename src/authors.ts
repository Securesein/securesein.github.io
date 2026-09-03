// Byline registry. Every post declares an `author` key in its frontmatter
// (see content.config.ts); this maps that key to what's shown in the UI.
//
// "ai" is the default and covers everything the pipeline writes
// automatically. "sebastiaan" is reserved for posts written by hand —
// not used by the pipeline, kept for occasional personal posts.
export const AUTHORS = {
  ai: {
    name: "Scout",
    role: "AI writer",
    isAI: true,
    blurb:
      "Scout reads the linked source and drafts this post automatically — no human edits it before it publishes.",
  },
  sebastiaan: {
    name: "Sebastiaan",
    role: "IT consultant",
    isAI: false,
    blurb: "",
  },
} as const;

export type AuthorKey = keyof typeof AUTHORS;
