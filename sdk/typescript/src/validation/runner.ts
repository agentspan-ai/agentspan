/**
 * Validation runner — CLI entry point for @agentspan-ai/sdk/validation.
 *
 * Loads runs.toml config, executes examples concurrently, optionally invokes
 * an LLM judge, and generates an HTML report.
 */

export type {
  JudgeConfig,
  RunConfig,
  ValidationConfig,
} from './config.js';
export { parseToml, loadConfig } from './config.js';

export type { JudgeRubric, JudgeResult } from './judge.js';
export { judgeResult } from './judge.js';

export type { RunReport } from './report.js';
export { generateReport } from './report.js';

// ── CLI argument parsing ─────────────────────────────────

export interface RunnerArgs {
  /** Filter to a single run by name. */
  run?: string;
  /** Filter runs by group. */
  group?: string;
  /** Print what would run without executing. */
  dryRun?: boolean;
  /** Invoke LLM judge after execution. */
  judge?: boolean;
  /** Generate an HTML report at the given path. */
  report?: string;
  /** Resume from a previous partial run (fixture directory). */
  resume?: string;
  /** Path to runs.toml config. */
  config?: string;
}

/**
 * Parse CLI arguments into RunnerArgs.
 *
 * Supports: --run <name>, --group <name>, --dry-run, --judge,
 *           --report <path>, --resume <dir>, --config <path>
 */
export function parseArgs(argv: string[]): RunnerArgs {
  const args: RunnerArgs = {};

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '--run':
        args.run = argv[++i];
        break;
      case '--group':
        args.group = argv[++i];
        break;
      case '--dry-run':
        args.dryRun = true;
        break;
      case '--judge':
        args.judge = true;
        break;
      case '--report':
        args.report = argv[++i];
        break;
      case '--resume':
        args.resume = argv[++i];
        break;
      case '--config':
        args.config = argv[++i];
        break;
    }
  }

  return args;
}

// ── Run filtering ────────────────────────────────────────

import type { RunConfig, ValidationConfig } from './config.js';
import type { RunReport } from './report.js';

/**
 * Filter runs based on --run and --group arguments.
 */
export function filterRuns(
  runs: RunConfig[],
  args: RunnerArgs,
): RunConfig[] {
  let filtered = runs;
  if (args.run) {
    filtered = filtered.filter((r) => r.name === args.run);
  }
  if (args.group) {
    filtered = filtered.filter((r) => r.group === args.group);
  }
  return filtered;
}

/**
 * Execute validation runs concurrently.
 *
 * Each run is an entry from runs.toml. The executor callback should
 * return a RunReport for each run config.
 */
export async function executeRuns(
  runs: RunConfig[],
  executor: (run: RunConfig) => Promise<RunReport>,
): Promise<RunReport[]> {
  const promises = runs.map((run) =>
    executor(run).catch(
      (err): RunReport => ({
        name: run.name,
        model: run.model,
        group: run.group,
        status: 'FAILED',
        finishReason: 'error',
        error: String(err),
      }),
    ),
  );

  const results = await Promise.allSettled(promises);
  return results.map((r) => {
    if (r.status === 'fulfilled') return r.value;
    return {
      name: 'unknown',
      model: 'unknown',
      status: 'FAILED',
      finishReason: 'error',
      error: String(r.reason),
    };
  });
}

/**
 * Print a summary of validation results to stdout.
 */
export function printSummary(results: RunReport[]): void {
  const passed = results.filter(
    (r) => r.status === 'COMPLETED' && (r.judgeResult?.passed ?? true),
  ).length;
  const failed = results.length - passed;

  console.log('\n=== Validation Summary ===');
  console.log(`Total: ${results.length}`);
  console.log(`Passed: ${passed}`);
  console.log(`Failed: ${failed}`);
  console.log('');

  for (const r of results) {
    const icon =
      r.status === 'COMPLETED' && (r.judgeResult?.passed ?? true)
        ? '[PASS]'
        : '[FAIL]';
    const score = r.judgeResult
      ? ` (score: ${r.judgeResult.weightedAverage.toFixed(2)})`
      : '';
    console.log(`  ${icon} ${r.name} [${r.model}]${score}`);
    if (r.error) {
      console.log(`        Error: ${r.error}`);
    }
  }
}
