/**
 * Content lint — the rules the Zod schema cannot express.
 *
 * The schema in src/content.config.ts is the main gate: anything it
 * rejects fails `astro build`, and that is where every rule that must
 * hold for *new* posts lives. Three things cannot live there.
 *
 * WARNINGS (exit 0) — the grandfathered archive. Posts published before
 * SCHEMA_CUTOVER predate the structured `source` field, and posts
 * published before AUTONOMY_CUTOVER predate the `release` and `scout`
 * blocks entirely. Rather than express "warn, don't fail" inside Zod —
 * which it has no clean way to say — the schema hard-fails only from
 * each cutover onward and the older stragglers are reported here. The
 * list shrinks on its own and should never grow.
 *
 * ERRORS (exit 1) — two hard checks:
 *
 *   1. Referential integrity of `benchmarkRefs` against the
 *      `benchmarks` collection (brief §4.1 rule 4, and gate G5 of §10).
 *      Cross-collection, so a per-entry Zod schema has no way to see
 *      it, and it must be a hard failure: a post citing a measurement
 *      that does not exist is exactly the invented-number failure the
 *      whole verification design is there to prevent.
 *
 *   2. Route coverage. Every section in taxonomy.json declares an
 *      `href`, and a section whose landing page does not exist is a
 *      404 in the header nav. Adding a section to the vocabulary
 *      without adding its route should fail loudly rather than ship.
 *
 * Run: `npm run check:content`. Wired into deploy.yml *without*
 * continue-on-error, so an integrity error fails the workflow.
 */
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import yaml from "js-yaml";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BLOG_DIR = join(ROOT, "src", "content", "blog");
const BENCHMARK_DIR = join(ROOT, "src", "content", "benchmarks");
const PAGES_DIR = join(ROOT, "src", "pages");

// Keep in step with src/content.config.ts.
const SCHEMA_CUTOVER = new Date("2026-09-12T00:00:00Z");
const AUTONOMY_CUTOVER = new Date("2026-09-14T00:00:00Z");

const taxonomy = JSON.parse(
  readFileSync(join(ROOT, "taxonomy.json"), "utf8")
);

function readFrontmatter(file) {
  const text = readFileSync(join(BLOG_DIR, file), "utf8");
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!match) return null;
  return yaml.load(match[1]);
}

/** Every measurement id in the collection — the filename is the id. */
function measurementIds() {
  if (!existsSync(BENCHMARK_DIR)) return new Set();
  return new Set(
    readdirSync(BENCHMARK_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.slice(0, -".json".length))
  );
}

const warnings = [];
const errors = [];
const known = measurementIds();

// The grandfathered archive produces one identical line per post, which
// buries everything else. Collect those by rule and print a count plus
// the slugs on one line instead.
const grandfathered = new Map();
const grandfather = (rule, slug) => {
  if (!grandfathered.has(rule)) grandfathered.set(rule, []);
  grandfathered.get(rule).push(slug);
};

// --- every section in the vocabulary has a landing page -------------
for (const [slug, info] of Object.entries(taxonomy.sections)) {
  const route = info.href.replace(/^\/|\/$/g, "");
  const page = join(PAGES_DIR, route, "index.astro");
  if (!existsSync(page)) {
    errors.push(
      `taxonomy.json declares section "${slug}" at ${info.href}, but ` +
        `src/pages/${route}/index.astro does not exist — the header nav ` +
        `would link to a 404.`
    );
  }
  const feed = join(PAGES_DIR, route, "rss.xml.ts");
  if (!existsSync(feed)) {
    warnings.push(
      `section "${slug}" has no feed at ${info.href}/rss.xml — every other ` +
        `section has one.`
    );
  }
}

for (const file of readdirSync(BLOG_DIR).filter((f) => f.endsWith(".md"))) {
  const data = readFrontmatter(file);
  if (!data) {
    warnings.push(`${file}: no frontmatter block`);
    continue;
  }

  const pubDate = new Date(data.pubDate);

  const slug = file.slice(0, -".md".length);

  if (data.credit === "scout" && !data.source && pubDate < SCHEMA_CUTOVER) {
    grandfather(
      "Scout posts with no `source` (pre-schema-cutover). Add one if the " +
        "original URL turns up",
      slug
    );
  }

  if (data.credit === "scout" && !data.scout && pubDate < AUTONOMY_CUTOVER) {
    grandfather(
      "Scout posts with no `scout` block (pre-autonomy-cutover) — no " +
        "qualityScore, relevanceScore or whyRelevant, because two-stage " +
        "scoring did not exist when they were published. Never back-fill one",
      slug
    );
  }

  if (data.kind === "release" && !data.release && pubDate < AUTONOMY_CUTOVER) {
    grandfather(
      "Model Updates posts with no `release` block (pre-autonomy-cutover), " +
        "so entity dedup cannot see them. Never invent an eventType for one",
      slug
    );
  }

  if (data.credit !== "written" && !data.model) {
    warnings.push(
      `${file}: no \`model\` set, so the "How this was made" block cannot ` +
        `name what drafted it.`
    );
  }

  // --- hard: benchmarkRefs must resolve (§4.1 rule 4 / gate G5) -----
  for (const id of data.benchmarkRefs ?? []) {
    if (!known.has(id)) {
      errors.push(
        `${file}: benchmarkRefs cites "${id}", which is not a measurement in ` +
          `src/content/benchmarks/. A post may only cite numbers that exist ` +
          `in the collection.`
      );
    }
  }
}

if (grandfathered.size > 0) {
  console.log("Grandfathered archive (expected; the list only ever shrinks):\n");
  for (const [rule, slugs] of grandfathered) {
    console.log(`  • ${slugs.length} × ${rule}.`);
    console.log(`      ${slugs.join(", ")}`);
  }
  console.log("");
}

if (warnings.length === 0) {
  console.log("Content warnings: none.");
} else {
  console.log(`Content warnings (${warnings.length}) — informational only:\n`);
  for (const w of warnings) console.log(`  • ${w}`);
}

if (errors.length > 0) {
  console.error(`\nContent ERRORS (${errors.length}) — these fail the build:\n`);
  for (const e of errors) console.error(`  ✗ ${e}`);
  process.exit(1);
}
