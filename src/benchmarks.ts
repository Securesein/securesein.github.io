// Query layer for the `benchmarks` collection, in the same spirit as
// src/posts.ts: every route asks its questions here, so "what counts as
// current", "how is a score formatted" and "how are conditions
// summarised" have exactly one answer each.
import { getCollection, type CollectionEntry } from "astro:content";
import { BENCHMARKS, BENCHMARK_ORDER, modelName } from "./registries";

export type Measurement = CollectionEntry<"benchmarks">;

/** How a record got its number. Vendor claims are shown, never hidden —
 *  the contrast with a third-party run is the product. */
export const MEASURED_BY: Record<
  string,
  { label: string; title: string }
> = {
  vendor: {
    label: "Vendor",
    title: "Reported by the model's own vendor",
  },
  thirdparty: {
    label: "Third party",
    title: "Measured independently of the vendor",
  },
  community: {
    label: "Community",
    title: "Community-run leaderboard submission",
  },
};

const byDateDesc = (a: Measurement, b: Measurement) =>
  b.data.measuredAt.valueOf() - a.data.measuredAt.valueOf();

/**
 * A record replaced by a later run of the same thing is history, not a
 * current reading, so the tracker drops it. The link runs forward
 * (`supersedes` points back), so "superseded" means "some other record
 * names me".
 */
async function currentMeasurements(): Promise<Measurement[]> {
  const all = await getCollection("benchmarks");
  const superseded = new Set(
    all.map((m) => m.data.supersedes).filter((id): id is string => !!id)
  );
  return all.filter((m) => !superseded.has(m.id));
}

export async function allMeasurements(): Promise<Measurement[]> {
  return (await currentMeasurements()).sort(byDateDesc);
}

export interface BenchmarkGroup {
  slug: string;
  name: string;
  description: string;
  homepage: string;
  unit: string;
  rows: Measurement[];
  /** How many current records exist, before the per-table cap. */
  total: number;
}

/**
 * The tracker, one section per benchmark, registry order.
 *
 * Within a benchmark, a model can hold several current records — a
 * vendor claim and an independent run, or two reasoning efforts — and
 * all of them belong in the table: the whole point is to be able to see
 * them next to each other. Rows are ordered by score, best first
 * (respecting `higherIsBetter`), and capped so one saturated benchmark
 * cannot turn the page into a thousand-row scroll.
 */
export async function benchmarkGroups(limit = 25): Promise<BenchmarkGroup[]> {
  const all = await currentMeasurements();
  const groups: BenchmarkGroup[] = [];

  for (const slug of BENCHMARK_ORDER) {
    const info = BENCHMARKS[slug];
    const rows = all.filter((m) => m.data.benchmark === slug);
    if (rows.length === 0) continue;

    rows.sort((a, b) => {
      const diff = info.higherIsBetter
        ? b.data.value - a.data.value
        : a.data.value - b.data.value;
      return diff !== 0 ? diff : byDateDesc(a, b);
    });

    groups.push({
      slug,
      name: info.name,
      description: info.description,
      homepage: info.homepage,
      unit: info.unit,
      rows: rows.slice(0, limit),
      total: rows.length,
    });
  }
  return groups;
}

/** Distinct attribution lines across the loaded data, for the credit
 *  block under the table. CC-BY is a condition, not a courtesy. */
export async function attributions(): Promise<string[]> {
  const seen = new Set<string>();
  for (const m of await currentMeasurements()) {
    const line = m.data.attribution ?? m.data.publisher;
    if (line) seen.add(line);
  }
  return [...seen].sort();
}

export function formatValue(m: Measurement): string {
  const { value, unit } = m.data;
  switch (unit) {
    case "percent":
      return `${value.toFixed(1)}%`;
    case "elo":
      return Math.round(value).toString();
    case "usd":
      return `$${value.toFixed(2)}`;
    case "seconds":
      return `${value.toFixed(1)}s`;
    default:
      return value.toFixed(1);
  }
}

/**
 * One short line of the conditions that actually move a score. Kept
 * terse because it sits in a table cell, but never empty: the schema
 * refuses a measurement with nothing in `conditions`, and a blank cell
 * here would quietly undo that.
 */
const NOTE_LIMIT = 90;

export function conditionsSummary(m: Measurement): string {
  const c = m.data.conditions;
  const parts: string[] = [];
  if (c.reasoningEffort) parts.push(`effort ${c.reasoningEffort}`);
  if (c.shots !== undefined) parts.push(c.shots === 0 ? "zero-shot" : `${c.shots}-shot`);
  if (c.tools !== undefined) parts.push(c.tools ? "tools" : "no tools");
  if (c.temperature !== undefined) parts.push(`temp ${c.temperature}`);
  if (m.data.harness) parts.push(m.data.harness);
  // The full note stays in the record — conditions travel with the
  // number, and truncating the data would undo the point of the
  // collection. What gets trimmed is the table cell: an evaluator's
  // standing house conditions repeated verbatim on a thousand rows is
  // noise, and the same sentence is stated once under the table.
  if (c.notes) {
    parts.push(
      c.notes.length > NOTE_LIMIT ? `${c.notes.slice(0, NOTE_LIMIT).trimEnd()}…` : c.notes
    );
  }
  return parts.join(" · ");
}

/** The untruncated conditions, for the row's `title` tooltip. */
export function conditionsFull(m: Measurement): string {
  const c = m.data.conditions;
  return [
    c.reasoningEffort && `reasoning effort: ${c.reasoningEffort}`,
    c.shots !== undefined && `${c.shots}-shot`,
    c.tools !== undefined && (c.tools ? "tools available" : "no tools"),
    c.temperature !== undefined && `temperature ${c.temperature}`,
    m.data.harness && `harness: ${m.data.harness}`,
    c.notes,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function label(m: Measurement): string {
  return modelName(m.data.model);
}
