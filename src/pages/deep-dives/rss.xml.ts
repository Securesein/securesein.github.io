import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../../consts";
import { postsOfFormat } from "../../posts";
import { feedItem } from "../../feeds";
import { FORMATS } from "../../taxonomy";

// Kept at its existing URL: this feed has been published for a while
// and a subscriber should not lose it because the axis it names moved
// from `kind` to `format`.
export async function GET(context: APIContext) {
  const posts = await postsOfFormat("deepdive");
  return rss({
    title: `${SITE.title} — Deep dives`,
    description: FORMATS.deepdive.description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
