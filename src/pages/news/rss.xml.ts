import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../../consts";
import { postsOfFormat } from "../../posts";
import { feedItem } from "../../feeds";
import { FORMATS } from "../../taxonomy";

// A FORMAT feed now, not a section feed — see src/pages/news/[...page].astro.
export async function GET(context: APIContext) {
  const posts = await postsOfFormat("news");
  return rss({
    title: `${SITE.title} — News`,
    description: FORMATS.news.description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
