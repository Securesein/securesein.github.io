import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../../consts";
import { postsOfKind } from "../../posts";
import { feedItem } from "../../feeds";
import { KINDS } from "../../taxonomy";

export async function GET(context: APIContext) {
  const posts = await postsOfKind("news");
  return rss({
    title: `${SITE.title} — News`,
    description: KINDS.news.description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
