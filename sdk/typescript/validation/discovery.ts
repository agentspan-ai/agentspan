/**
 * Example discovery — find examples by group and/or filter.
 *
 * Searches the examples/ directory for .ts files matching
 * group membership and name filters.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { GROUPS } from './groups.js';

/** Root examples directory (relative to this file's location). */
const EXAMPLES_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', 'examples');

/** Subdirectories containing framework-specific examples. */
const SUBDIRS = ['vercel-ai', 'langgraph', 'langchain', 'openai', 'adk'];

/**
 * Collect example names from a directory.
 *
 * @param dir - Directory to scan
 * @param prefix - Prefix for the name (e.g., "vercel-ai/")
 * @returns Array of example names (without .ts extension)
 */
function collectFromDir(dir: string, prefix: string): string[] {
  if (!fs.existsSync(dir)) return [];

  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.ts')).sort();
  return files.map((f) => `${prefix}${f.replace(/\.ts$/, '')}`);
}

/**
 * Get all known example names.
 */
function allExamples(): string[] {
  const examples: string[] = [];

  // Top-level examples
  examples.push(...collectFromDir(EXAMPLES_DIR, ''));

  // Subdirectory examples
  for (const subdir of SUBDIRS) {
    const subdirPath = path.join(EXAMPLES_DIR, subdir);
    examples.push(...collectFromDir(subdirPath, `${subdir}/`));
  }

  return examples;
}

/**
 * Discover examples by group and/or name filter.
 *
 * @param group - Group name from GROUPS (e.g., "SMOKE_TEST", "VERCEL_AI")
 * @param filter - Optional list of example name substrings to match
 * @returns Array of example names
 */
export function discoverExamples(
  group?: string,
  filter?: string[],
): string[] {
  let examples: string[];

  if (group) {
    const groupExamples = GROUPS[group];
    if (!groupExamples || groupExamples.length === 0) {
      console.warn(`WARNING: group '${group}' is empty or not defined in groups.ts`);
      return [];
    }
    examples = groupExamples;
  } else {
    examples = allExamples();
  }

  // Apply name filter
  if (filter && filter.length > 0) {
    examples = examples.filter((name) =>
      filter.some((f) => name.includes(f)),
    );
  }

  return examples;
}

/**
 * Resolve an example name to its full file path.
 *
 * @param exampleName - Example name (e.g., "01-basic-agent" or "vercel-ai/01-passthrough")
 * @returns Absolute path to the .ts file
 */
export function resolveExamplePath(exampleName: string): string {
  return path.join(EXAMPLES_DIR, `${exampleName}.ts`);
}

/**
 * Check if an example file exists.
 */
export function exampleExists(exampleName: string): boolean {
  return fs.existsSync(resolveExamplePath(exampleName));
}
