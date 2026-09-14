// Shared shape for every feed on the site.
//
// Per-section and per-topic feeds matter here specifically because the
// sections have wildly different volumes: someone who wants two
// benchmark readings a month should not have to take six model releases
// a week with them.
//
// The Radar is deliberately absent from every feed on this site
// (decision A3 — internal only).
import { CREDITS } from "./credit";
import { postUrl, type Post } from "./posts";
import { SECTION_INFO, FORMATS } from "./taxonomy";

export function feedItem(post: Post) {
  const section = SECTION_INFO[post.data.kind];
  const format = FORMATS[post.data.format];
  return {
    title: post.data.title,
    description: post.data.description,
    pubDate: post.data.pubDate,
    link: postUrl(post),
    // Enough context in the feed reader to tell a two-minute auto-draft
    // from a twenty-minute teardown without opening it.
    categories: [`${section.label} — ${format.label}`, ...post.data.topics],
    customData: `<author>${CREDITS[post.data.credit].byline}</author>`,
  };
}
