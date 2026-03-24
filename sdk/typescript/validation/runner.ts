#!/usr/bin/env npx tsx
/**
 * Validation runner — CLI entry point for the TypeScript SDK validation framework.
 *
 * Usage:
 *   npx tsx validation/runner.ts --config validation/runs.toml.example
 *   npx tsx validation/runner.ts --config runs.toml --group SMOKE_TEST
 *   npx tsx validation/runner.ts --config runs.toml --judge --report
 *   npx tsx validation/runner.ts --config runs.toml --dry-run
 *   npx tsx validation/runner.ts --config runs.toml --run smoke,vercel_native
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { parseToml, type RunConfig, type ValidationConfig } from './config.js';
import { discoverExamples, resolveExamplePath, exampleExists } from './discovery.js';
import { executeExample, type ExecutionResult } from './executor.js';
import { runAlgorithmicChecks, determineStatus } from './checks/algorithmic.js';
import { isFrameworkPassthrough } from './groups.js';
import { judgeOutput, judgeComparison, type JudgeConfig } from './judge/llm.js';
import { JudgeCache, hashOutput } from './judge/cache.js';
import { saveResults } from './reporting/json.js';
import { generateHtmlReport } from './reporting/html.js';
import type { ValidationResult } from './types.js';

// ── CLI argument parsing ──────────────────────────────────

interface CliArgs {
  config?: string;
  group?: string;
  run?: string;
  judge: boolean;
  report: boolean;
  dryRun: boolean;
  native: boolean;
  outputDir: string;
}

function parseCliArgs(argv: string[]): CliArgs {
  const args: CliArgs = {
    judge: false,
    report: false,
    dryRun: false,
    native: false,
    outputDir: 'output',
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '--config':
        args.config = argv[++i];
        break;
      case '--group':
        args.group = argv[++i];
        break;
      case '--run':
        args.run = argv[++i];
        break;
      case '--judge':
        args.judge = true;
        break;
      case '--report':
        args.report = true;
        break;
      case '--dry-run':
        args.dryRun = true;
        break;
      case '--native':
        args.native = true;
        break;
      case '--output-dir':
        args.outputDir = argv[++i];
        break;
    }
  }

  return args;
}

// ── Concurrency limiter ───────────────────────────────────

async function withConcurrency<T>(
  items: T[],
  concurrency: number,
  fn: (item: T) => Promise<unknown>,
): Promise<void> {
  const active: Promise<void>[] = [];
  for (const item of items) {
    const p = fn(item).then(() => {
      active.splice(active.indexOf(p), 1);
    });
    active.push(p);
    if (active.length >= concurrency) {
      await Promise.race(active);
    }
  }
  await Promise.all(active);
}

// ── Extract prompt from example source ────────────────────

function extractPrompt(examplePath: string): string {
  if (!fs.existsSync(examplePath)) return 'unknown prompt';

  const source = fs.readFileSync(examplePath, 'utf-8');

  // Match runtime.run(agent, "prompt") or runtime.stream(agent, "prompt")
  const patterns = [
    /\.(?:run|stream)\s*\(\s*\w+\s*,\s*["'`]([^"'`]+)["'`]/,
    /\.(?:run|stream)\s*\(\s*\w+\s*,\s*\n\s*["'`]([^"'`]+)["'`]/,
    /prompt\s*[:=]\s*["'`]([^"'`]+)["'`]/,
  ];

  for (const pattern of patterns) {
    const match = pattern.exec(source);
    if (match) return match[1];
  }

  return 'unknown prompt';
}

// ── Single run execution ──────────────────────────────────

async function runSingle(
  runConfig: RunConfig,
  examples: string[],
  cliArgs: CliArgs,
  judgeConfig: JudgeConfig | null,
  cache: JudgeCache | null,
): Promise<ValidationResult[]> {
  const results: ValidationResult[] = [];

  const env: Record<string, string> = {
    ...(runConfig.env ?? {}),
    AGENTSPAN_SERVER_URL: runConfig.serverUrl ?? 'http://localhost:8080/api',
  };

  if (runConfig.model) {
    env['AGENTSPAN_MODEL'] = runConfig.model;
  }

  const maxWorkers = runConfig.parallel !== false ? (runConfig.maxWorkers ?? 8) : 1;
  const timeout = runConfig.timeout ?? 300;

  await withConcurrency(examples, maxWorkers, async (exampleName) => {
    const examplePath = resolveExamplePath(exampleName);

    if (!exampleExists(exampleName)) {
      console.log(`  [SKIP] ${exampleName} (file not found)`);
      results.push({
        example: exampleName,
        status: 'FAIL',
        duration: 0,
        checks: {
          workflowCompleted: false,
          noUnhandledErrors: true,
          toolAudit: [],
          allToolsSucceeded: true,
          llmEngaged: false,
          outputNonEmpty: false,
        },
        output: '',
        events: [],
        error: 'Example file not found',
      });
      return;
    }

    const startTime = Date.now();
    let exec: ExecutionResult;

    try {
      exec = await executeExample(
        examplePath,
        env,
        timeout,
        runConfig.native ?? cliArgs.native,
      );
    } catch (err) {
      const duration = (Date.now() - startTime) / 1000;
      console.log(`  [ERROR] ${exampleName} (${duration.toFixed(1)}s): ${err}`);
      results.push({
        example: exampleName,
        status: 'FAIL',
        duration,
        checks: {
          workflowCompleted: false,
          noUnhandledErrors: false,
          toolAudit: [],
          allToolsSucceeded: true,
          llmEngaged: false,
          outputNonEmpty: false,
        },
        output: '',
        events: [],
        error: String(err),
      });
      return;
    }

    // Run algorithmic checks
    const isPassthrough = isFrameworkPassthrough(exampleName);
    const checks = runAlgorithmicChecks(
      {
        status: exec.status,
        output: exec.output,
        events: exec.events,
      },
      { isFrameworkPassthrough: isPassthrough },
    );

    // LLM judge (optional)
    let judgeScore: number | undefined;
    let judgeReason: string | undefined;

    if (cliArgs.judge && judgeConfig) {
      const outputHash = hashOutput(exec.output);
      const cached = cache?.getScore(exampleName, outputHash);

      if (cached) {
        judgeScore = cached.score;
        judgeReason = cached.reason;
      } else if (exec.output.trim()) {
        const prompt = extractPrompt(examplePath);
        try {
          const result = await judgeOutput(prompt, exec.output, judgeConfig);
          judgeScore = result.score;
          judgeReason = result.reason;
          cache?.setScore(exampleName, outputHash, result.score, result.reason);
        } catch (err) {
          judgeReason = `Judge error: ${err}`;
        }
      }
    }

    const status = determineStatus(checks, judgeScore);
    const icon = status === 'PASS' ? '[PASS]' : status === 'WARN' ? '[WARN]' : '[FAIL]';
    const scoreStr = judgeScore != null ? ` (score: ${judgeScore})` : '';
    console.log(`  ${icon} ${exampleName} [${exec.duration.toFixed(1)}s]${scoreStr}`);

    results.push({
      example: exampleName,
      status,
      duration: exec.duration,
      checks,
      judgeScore,
      judgeReason,
      output: exec.output,
      events: exec.events,
      error: exec.status === 'FAILED' || exec.status === 'ERROR'
        ? exec.stderr.slice(0, 500) || 'Execution failed'
        : undefined,
    });
  });

  return results;
}

// ── Main ──────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));

  if (!args.config) {
    console.error('ERROR: --config <path> is required');
    console.error('Usage: npx tsx validation/runner.ts --config validation/runs.toml.example [options]');
    console.error('');
    console.error('Options:');
    console.error('  --config <path>     Path to TOML config file (required)');
    console.error('  --group <name>      Filter to examples in this group');
    console.error('  --run <names>       Filter to specific runs (comma-separated)');
    console.error('  --judge             Enable LLM judge scoring');
    console.error('  --report            Generate HTML report');
    console.error('  --dry-run           List examples without executing');
    console.error('  --native            Force native framework execution');
    console.error('  --output-dir <dir>  Output directory (default: output)');
    process.exit(1);
  }

  // Load config
  const configPath = path.resolve(args.config);
  if (!fs.existsSync(configPath)) {
    console.error(`ERROR: Config file not found: ${configPath}`);
    process.exit(1);
  }

  const configContent = fs.readFileSync(configPath, 'utf-8');
  const config: ValidationConfig = parseToml(configContent);

  if (config.runs.length === 0) {
    console.error('ERROR: No runs defined in config file.');
    process.exit(1);
  }

  // Filter runs
  let runs = config.runs;
  if (args.run) {
    const selectedNames = args.run.split(',').map((s) => s.trim());
    runs = runs.filter((r) => selectedNames.includes(r.name));
    if (runs.length === 0) {
      const available = config.runs.map((r) => r.name).join(', ');
      console.error(`ERROR: No matching runs. Available: ${available}`);
      process.exit(1);
    }
  }

  // Override group from CLI
  if (args.group) {
    runs = runs.map((r) => ({ ...r, group: args.group }));
  }

  console.log('');
  console.log('=== Agentspan TypeScript SDK Validation ===');
  console.log(`Config: ${configPath}`);
  console.log(`Runs: ${runs.map((r) => r.name).join(', ')}`);
  console.log('');

  // Initialize judge cache
  const cache = args.judge
    ? new JudgeCache(path.join(args.outputDir, 'judge_cache.json'))
    : null;

  const judgeConfig: JudgeConfig | null = args.judge
    ? {
        model: config.judge.model,
        maxTokens: config.judge.maxTokens,
        maxOutputChars: config.judge.maxOutputChars,
      }
    : null;

  const allResults: ValidationResult[] = [];

  for (const runConfig of runs) {
    console.log(`--- Run: ${runConfig.name} (model: ${runConfig.model}) ---`);

    // Discover examples for this run
    const examples = discoverExamples(runConfig.group);

    if (examples.length === 0) {
      console.log(`  No examples found${runConfig.group ? ` for group ${runConfig.group}` : ''}`);
      continue;
    }

    console.log(`  Examples: ${examples.length}`);

    if (args.dryRun) {
      for (const ex of examples) {
        const exists = exampleExists(ex);
        console.log(`    ${exists ? '[OK]' : '[MISSING]'} ${ex}`);
      }
      continue;
    }

    // Execute
    const results = await runSingle(runConfig, examples, args, judgeConfig, cache);
    allResults.push(...results);

    // Print run summary
    const passed = results.filter((r) => r.status === 'PASS').length;
    const failed = results.filter((r) => r.status === 'FAIL').length;
    const warned = results.filter((r) => r.status === 'WARN').length;
    console.log(`  Summary: ${passed} passed, ${failed} failed, ${warned} warned`);
    console.log('');
  }

  if (args.dryRun) {
    console.log('\nDry run complete. No examples were executed.');
    return;
  }

  // Save cache
  cache?.save();

  // Save JSON results
  if (allResults.length > 0) {
    saveResults(allResults, args.outputDir);
    console.log(`Results saved to ${args.outputDir}/results.json`);
  }

  // Generate HTML report
  if (args.report && allResults.length > 0) {
    const reportPath = path.join(args.outputDir, 'report.html');
    generateHtmlReport(allResults, reportPath);
    console.log(`HTML report saved to ${reportPath}`);
  }

  // Final summary
  const totalPassed = allResults.filter((r) => r.status === 'PASS').length;
  const totalFailed = allResults.filter((r) => r.status === 'FAIL').length;
  const totalWarned = allResults.filter((r) => r.status === 'WARN').length;

  console.log('');
  console.log('=== Final Summary ===');
  console.log(`Total: ${allResults.length}`);
  console.log(`Passed: ${totalPassed}`);
  console.log(`Failed: ${totalFailed}`);
  console.log(`Warned: ${totalWarned}`);

  if (totalFailed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
