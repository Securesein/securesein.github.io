// Shared shape for every feed on the site.
//
// Per-lane and per-topic feeds matter here specifically because the
// lanes have wildly different volumes: someone who wants four deep
// dives a month should not have to take forty Scout items with them.
import { CREDITS } from "./credit";
import { postUrl, type Post } from "./posts";
import { KINDS, FORMATS } from "./taxonomy";

export function feedItem(post: Post) {
  const kind = KINDS[post.data.kind];
  const format = post.data.format ? FORMATS[post.data.format] : undefined;
  return {
    title: post.data.title,
    description: post.data.description,
    pubDate: post.data.pubDate,
    link: postUrl(post),
    // Enough context in the feed reader to tell a two-minute auto-draft
    // from a twenty-minute teardown without opening it.
    categories: [
      format ? `${kind.label} — ${format.label}` : kind.label,
      ...post.data.topics,
    ],
    customData: `<author>${CREDITS[post.data.credit].byline}</author>`,
  };
}
