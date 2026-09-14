import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../../consts";
import { postsOfKind } from "../../posts";
import { feedItem } from "../../feeds";
import { SECTION_INFO } from "../../taxonomy";

const SECTION = "release" as const;

export async function GET(context: APIContext) {
  const posts = await postsOfKind(SECTION);
  return rss({
    title: `${SITE.title} — ${SECTION_INFO[SECTION].label}`,
    description: SECTION_INFO[SECTION].description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
