import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../../consts";
import { postsOfKind } from "../../posts";
import { feedItem } from "../../feeds";
import { KINDS } from "../../taxonomy";

export async function GET(context: APIContext) {
  const posts = await postsOfKind("deepdive");
  return rss({
    title: `${SITE.title} — Deep dives`,
    description: KINDS.deepdive.description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
