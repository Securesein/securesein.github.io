// @ts-check
import { defineConfig } from "astro/config";

function remarkReadingTime() {
  return function (tree, file) {
    const text = toText(tree);
    const words = text.split(/\s+/).filter(Boolean).length;
    const minutes = Math.max(1, Math.round(words / 200));
    file.data.astro.frontmatter.minutesRead = `${minutes} min read`;
  };
}

function toText(node) {
  if (node.value) return node.value;
  if (node.children) return node.children.map(toText).join(" ");
  return "";
}

export default defineConfig({
  site: "https://securesein.github.io",
  markdown: {
    remarkPlugins: [remarkReadingTime],
  },
  // Individual post URLs never change — /blog/<slug>/ is already
  // indexed and shared, and GitHub Pages has no server-side redirects
  // to soften a rename with. Only the two routes that stopped existing
  // get one, and in a static build Astro emits each as a small
  // meta-refresh page.
  redirects: {
    // /blog was the News listing before the three lanes existed.
    "/blog": "/news/",
    // The "Welcome to securesein" post; its content now lives on About.
    "/blog/welcome": "/about/",
  },
});
