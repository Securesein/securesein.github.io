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
  site: "https://sebastiaan.github.io",
  markdown: {
    remarkPlugins: [remarkReadingTime],
  },
});
