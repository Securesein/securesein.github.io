// Shared query layer for the blog collection.
//
// Every route asks its questions through here rather than repeating a
// getCollection + filter + sort in each page, so "what counts as
// published", "what order does this lane use" and "how is reading time
// measured" have exactly one answer each.
import { getCollection, type CollectionEntry } from "astro:content";
import { KIND_ORDER_BY_DEPTH, type Kind, type Topic } from "./taxonomy";

export type Post = CollectionEntry<"blog">;
export type Thread = CollectionEntry<"threads">;

const isPublished = ({ data }: Post) => !data.draft;

const byDateDesc = (a: Post, b: Post) =>
  b.data.pubDate.valueOf() - a.data.pubDate.valueOf();

/**
 * Fundamentals is a reading path, not a feed: an explicit `order`
 * wins, and anything without one falls to the end in publication
 * order. Sorting evergreen explainers by recency actively misleads a
 * newcomer about where to start.
 */
const byReadingPath = (a: Post, b: Post) => {
  const ao = a.data.order ?? Number.MAX_SAFE_INTEGER;
  const bo = b.data.order ?? Number.MAX_SAFE_INTEGER;
  if (ao !== bo) return ao - bo;
  return a.data.pubDate.valueOf() - b.data.pubDate.valueOf();
};

/** Every published post, newest first. */
export async function allPosts(): Promise<Post[]> {
  return (await getCollection("blog", isPublished)).sort(byDateDesc);
}

/** Published posts in one lane. Fundamentals comes back in path order. */
export async function postsOfKind(kind: Kind): Promise<Post[]> {
  const posts = (await getCollection("blog", isPublished)).filter(
    (p) => p.data.kind === kind
  );
  return posts.sort(kind === "explainer" ? byReadingPath : byDateDesc);
}

/** Published posts on one subject shelf, newest first. */
export async function postsByTopic(topic: Topic): Promise<Post[]> {
  return (await getCollection("blog", isPublished))
    .filter((p) => (p.data.topics as Topic[]).includes(topic))
    .sort(byDateDesc);
}

/** How many published posts each topic holds — for the topic directory. */
export async function topicCounts(): Promise<Record<string, number>> {
  const counts: Record<string, number> = {};
  for (const post of await getCollection("blog", isPublished)) {
    for (const topic of post.data.topics) {
      counts[topic] = (counts[topic] ?? 0) + 1;
    }
  }
  return counts;
}

/** Post URLs never change shape — /blog/<slug>/ stays as it is. */
export function postUrl(post: Post | string): string {
  return `/blog/${typeof post === "string" ? post : post.id}/`;
}

/**
 * Reading time, measured from the raw markdown rather than the
 * rendered HTML so listings don't have to render every post they
 * link to. Same 200 wpm the remark plugin uses.
 */
export function readingMinutes(post: Post): number {
  const words = post.body?.split(/\s+/).filter(Boolean).length ?? 0;
  return Math.max(1, Math.round(words / 200));
}

/** Groups posts into day buckets, preserving the incoming order. */
export function groupByDay(posts: Post[]): { date: Date; posts: Post[] }[] {
  const groups: { date: Date; posts: Post[] }[] = [];
  for (const post of posts) {
    const key = post.data.pubDate.toISOString().slice(0, 10);
    const last = groups[groups.length - 1];
    if (last && last.date.toISOString().slice(0, 10) === key) {
      last.posts.push(post);
    } else {
      groups.push({ date: post.data.pubDate, posts: [post] });
    }
  }
  return groups;
}

/** Groups posts by kind, best material first (deep dives → news). */
export function groupByKind(posts: Post[]): { kind: Kind; posts: Post[] }[] {
  return KIND_ORDER_BY_DEPTH.map((kind) => ({
    kind,
    posts: posts.filter((p) => p.data.kind === kind),
  })).filter((group) => group.posts.length > 0);
}

/** Every thread, with its posts resolved and any missing ids dropped. */
export async function threadsWithPosts(): Promise<
  { thread: Thread; posts: Post[] }[]
> {
  const [threads, posts] = await Promise.all([
    getCollection("threads"),
    getCollection("blog", isPublished),
  ]);
  const byId = new Map(posts.map((p) => [p.id, p]));
  return threads.map((thread) => ({
    thread,
    posts: thread.data.posts
      .map((id) => byId.get(id))
      .filter((p): p is Post => p !== undefined),
  }));
}

export interface ThreadPosition {
  thread: Thread;
  index: number; // 1-based
  total: number;
  prev?: Post;
  next?: Post;
}

/**
 * Where this post sits in each thread it belongs to, so the post page
 * can render a "part 2 of 4" strip with working prev/next links.
 * Reads from the thread's own ordered list rather than the post's
 * `threads` array, so the curated order is the only source of order.
 */
export async function threadPositions(post: Post): Promise<ThreadPosition[]> {
  const positions: ThreadPosition[] = [];
  for (const { thread, posts } of await threadsWithPosts()) {
    const i = posts.findIndex((p) => p.id === post.id);
    if (i === -1) continue;
    positions.push({
      thread,
      index: i + 1,
      total: posts.length,
      prev: posts[i - 1],
      next: posts[i + 1],
    });
  }
  return positions;
}

/**
 * Related reading, in priority order:
 *   1. the rest of a thread this post belongs to
 *   2. same topic, *different* kind — so a news reader lands on the
 *      deep dive rather than another two-minute item
 *   3. same topic, same kind
 * The post superseded by a better one elsewhere never recommends
 * itself onward as if it were the good version.
 */
export async function relatedPosts(post: Post, limit = 3): Promise<Post[]> {
  const [all, threads] = await Promise.all([allPosts(), threadsWithPosts()]);
  const picked: Post[] = [];
  const seen = new Set([post.id]);

  const take = (candidate: Post | undefined) => {
    if (!candidate || seen.has(candidate.id) || picked.length >= limit) return;
    seen.add(candidate.id);
    picked.push(candidate);
  };

  for (const { thread, posts } of threads) {
    if (!post.data.threads.includes(thread.id)) continue;
    for (const p of posts) take(p);
  }

  const topics = post.data.topics as Topic[];
  const shares = (p: Post) =>
    (p.data.topics as Topic[]).some((t) => topics.includes(t));

  for (const p of all) if (shares(p) && p.data.kind !== post.data.kind) take(p);
  for (const p of all) if (shares(p)) take(p);

  return picked;
}
