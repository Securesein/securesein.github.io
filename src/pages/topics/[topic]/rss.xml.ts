import rss from "@astrojs/rss";
import type { APIContext, GetStaticPaths } from "astro";
import { SITE } from "../../../consts";
import { postsByTopic } from "../../../posts";
import { feedItem } from "../../../feeds";
import { TOPICS, type Topic } from "../../../taxonomy";

export const getStaticPaths: GetStaticPaths = () =>
  (Object.keys(TOPICS) as Topic[]).map((topic) => ({ params: { topic } }));

export async function GET(context: APIContext) {
  const topic = context.params.topic as Topic;
  const posts = await postsByTopic(topic);
  return rss({
    title: `${SITE.title} — ${TOPICS[topic].label}`,
    description: TOPICS[topic].description,
    site: context.site!,
    items: posts.map(feedItem),
  });
}
