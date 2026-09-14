import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../../consts";
import { postsOfKind } from "../../posts";
import { feedItem } from "../../feeds";
import { SECTION_INFO } from "../../taxonomy";

export async function GET(context: APIContext) {
  const posts = await postsOfKind("explainer");
  return rss({
    title: `${SITE.title} — Fundamentals`,
    description: SECTION_INFO.explainer.description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
