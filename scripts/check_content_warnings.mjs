/**
 * Non-blocking content lint.
 *
 * The Zod schema in src/content.config.ts is the hard gate: anything it
 * rejects fails `astro build`, and that is where every rule that must
 * hold for *new* posts lives. This script covers the one rule that
 * cannot be a hard gate without breaking the existing archive:
 *
 *   Scout posts must carry their source.
 *
 * Posts published before SCHEMA_CUTOVER predate the structured `source`
 * field, and a couple of them genuinely have no recoverable URL (the
 * "custom brief" flow had no source article to begin with). Rather than
 * express "warn, don't fail" inside Zod — which it has no clean way to
 * say — the schema hard-fails only from the cutover date onward, and
 * this script reports the older stragglers informationally.
 *
 * Run: `npm run check:content`. Wired into deploy.yml as a
 * continue-on-error step, so it shows up in the log without ever
 * blocking a deploy.
 */
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import yaml from "js-yaml";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BLOG_DIR = join(ROOT, "src", "content", "blog");

// Keep in step with SCHEMA_CUTOVER in src/content.config.ts.
const SCHEMA_CUTOVER = new Date("2026-09-12T00:00:00Z");

function readFrontmatter(file) {
  const text = readFileSync(join(BLOG_DIR, file), "utf8");
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!match) return null;
  return yaml.load(match[1]);
}

const warnings = [];

for (const file of readdirSync(BLOG_DIR).filter((f) => f.endsWith(".md"))) {
  const data = readFrontmatter(file);
  if (!data) {
    warnings.push(`${file}: no frontmatter block`);
    continue;
  }

  const pubDate = new Date(data.pubDate);

  if (data.credit === "scout" && !data.source) {
    if (pubDate < SCHEMA_CUTOVER) {
      warnings.push(
        `${file}: Scout post with no \`source\` (published ${data.pubDate}, ` +
          `before the schema cutover — grandfathered, not a build failure). ` +
          `Add one if the original URL turns up.`
      );
    }
    // On or after the cutover this is already a hard build error; the
    // schema, not this script, is what stops it.
  }

  if (data.kind === "news" && data.credit !== "scout") {
    warnings.push(
      `${file}: kind "news" with credit "${data.credit}" — unusual but ` +
        `allowed. Check it is deliberate.`
    );
  }

  if (data.credit !== "written" && !data.model) {
    warnings.push(
      `${file}: no \`model\` set, so the "How this was made" block cannot ` +
        `name what drafted it.`
    );
  }
}

if (warnings.length === 0) {
  console.log("Content warnings: none.");
} else {
  console.log(`Content warnings (${warnings.length}) — informational only:\n`);
  for (const w of warnings) console.log(`  • ${w}`);
}
