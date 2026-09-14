// The two closed vocabularies the Releases and Benchmarks channels run
// on. As with taxonomy.json, the data lives at the repo root rather
// than under src/ so the Python pipeline (scripts/core/registry.py)
// reads the identical bytes and the two halves of the system cannot
// drift apart.
//
// Kept free of any `astro:content` import on purpose: content.config.ts
// needs BENCHMARK_SLUGS to build its schema, and a module that reaches
// back into the content layer from there is a cycle.
import benchmarkRegistry from "../benchmarks.json";
import modelRegistry from "../models.json";

export interface BenchmarkInfo {
  slug: string;
  name: string;
  description: string;
  metric: string;
  unit: string;
  higherIsBetter: boolean;
  homepage: string;
}

export interface ModelInfo {
  id: string;
  vendor: string;
  family: string;
  displayName: string;
  aliases: string[];
  openWeights: boolean;
  releasedAt?: string;
}

const benchmarkData = benchmarkRegistry as { benchmarks: BenchmarkInfo[] };
const modelData = modelRegistry as { models: ModelInfo[] };

export const BENCHMARKS: Record<string, BenchmarkInfo> = Object.fromEntries(
  benchmarkData.benchmarks.map((b) => [b.slug, b])
);
export const MODELS: Record<string, ModelInfo> = Object.fromEntries(
  modelData.models.map((m) => [m.id, m])
);

export const BENCHMARK_SLUGS = benchmarkData.benchmarks.map((b) => b.slug) as [
  string,
  ...string[],
];

/** Registry order is the order the tracker renders sections in. */
export const BENCHMARK_ORDER: string[] = benchmarkData.benchmarks.map(
  (b) => b.slug
);

/**
 * Display name for a canonical model id. Falls back to the id itself
 * rather than throwing: a measurement can only exist for a registered
 * model, but a roundup post's `benchmarkRefs` could in principle
 * outlive a registry edit, and a missing label should degrade to a
 * readable slug rather than a blank cell.
 */
export function modelName(id: string): string {
  return MODELS[id]?.displayName ?? id;
}

export function vendorOf(id: string): string {
  return MODELS[id]?.vendor ?? "unknown";
}
