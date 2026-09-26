// @ts-check
import { readdirSync, readFileSync } from "node:fs";
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

/** @returns {import("unified").Transformer<any>} */
function remarkReadingTime() {
  /**
   * @param {any} tree
   * @param {any} file
   */
  return function (tree, file) {
    const text = toText(tree);
    const words = text.split(/\s+/).filter(Boolean).length;
    const minutes = Math.max(1, Math.round(words / 200));
    file.data.astro.frontmatter.minutesRead = `${minutes} min read`;
  };
}

/** @param {any} node @returns {string} */
function toText(node) {
  if (node.value) return node.value;
  if (node.children) return node.children.map(toText).join(" ");
  return "";
}

/**
 * slug -> last-changed date, read straight off the post files.
 *
 * The sitemap had no `lastmod` at all, which for a site that publishes
 * several times a day is the one hint worth giving a crawler: it is how
 * a search engine decides which of ~70 URLs are worth re-fetching
 * today. Read with a regex rather than a YAML parser on purpose — the
 * only two fields that matter are ISO dates on their own line, and a
 * file whose date cannot be read simply gets no lastmod rather than
 * breaking the build. An inaccurate lastmod is worse than none, so
 * `updatedDate` wins over `pubDate` where a post has one.
 */
function postDates() {
  const dir = new URL("./src/content/blog/", import.meta.url);
  const dates = new Map();
  let files = [];
  try {
    files = readdirSync(dir).filter((f) => f.endsWith(".md"));
  } catch {
    return dates; // no content dir (fresh clone, CI cache miss): no lastmod
  }
  for (const file of files) {
    try {
      const text = readFileSync(new URL(file, dir), "utf-8").slice(0, 2000);
      const updated = text.match(/^updatedDate:\s*"?(\d{4}-\d{2}-\d{2})/m);
      const published = text.match(/^pubDate:\s*"?(\d{4}-\d{2}-\d{2})/m);
      const stamp = (updated ?? published)?.[1];
      if (stamp) dates.set(file.replace(/\.md$/, ""), stamp);
    } catch {
      // One unreadable post must not cost the whole sitemap its dates.
    }
  }
  return dates;
}

const POST_DATES = postDates();

export default defineConfig({
  site: "https://securesein.com",
  markdown: {
    remarkPlugins: [remarkReadingTime],
  },
  integrations: [
    sitemap({
      // The two redirect stubs are meta-refresh pages, not content.
      filter: (page) => !/\/blog\/?$|\/blog\/welcome\/?$/.test(page),
      serialize(item) {
        const slug = item.url.match(/\/blog\/([^/]+)\/?$/)?.[1];
        const stamp = slug && POST_DATES.get(slug);
        return stamp ? { ...item, lastmod: new Date(stamp).toISOString() } : item;
      },
    }),
  ],
  // Individual post URLs never change — /blog/<slug>/ is already
  // indexed and shared, and GitHub Pages has no server-side redirects
  // to soften a rename with. Only the two routes that stopped existing
  // get one, and in a static build Astro emits each as a small
  // meta-refresh page.
  redirects: {
    // /blog was the News listing before the three lanes existed, and
    // pointed at /news/ until that listing was retired — it now goes
    // where /news/ goes rather than at a page that stopped existing.
    "/blog": "/research/",
    // The "Welcome to securesein" post; its content now lives on About.
    "/blog/welcome": "/about/",
    // The News listing is retired (content-architecture change). The
    // posts are untouched and still live at their own URLs; what went
    // away is the page that listed them by format. Research is where
    // that content belongs now, so the page and its feed send readers
    // there rather than 404ing — a feed especially, since subscribers
    // never find out one broke.
    "/news": "/research/",
    "/news/rss.xml": "/research/rss.xml",
  },
});
