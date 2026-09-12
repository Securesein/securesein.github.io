// Everything, in one feed. The per-lane feeds exist because this one
// is dominated by Scout's volume.
import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { SITE } from "../consts";
import { allPosts } from "../posts";
import { feedItem } from "../feeds";

export async function GET(context: APIContext) {
  const posts = await allPosts();
  return rss({
    title: SITE.title,
    description: SITE.description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
