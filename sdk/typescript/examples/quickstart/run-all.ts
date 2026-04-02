#!/usr/bin/env npx tsx
/**
 * Quickstart test harness — runs all examples in parallel and validates results.
 *
 * Assertions:
 *   a) All agents complete with status COMPLETED
 *   b) Each finishes within 30 seconds
 *   c) Tool calls (if any) completed successfully — no COMPLETED_WITH_ERRORS
 *   d) Guardrails (if any) completed successfully
 *
 * Usage:
 *   npx tsx quickstart/run-all.ts
 */

import { AgentRuntime } from '../../src/index.js';

import { agent as basicAgent, prompt as basicPrompt } from './01-basic-agent.js';
import { agent as toolsAgent, prompt as toolsPrompt } from './02-tools.js';
import { agent as multiAgent, prompt as multiPrompt } from './03-multi-agent.js';
import { agent as guardrailsAgent, prompt as guardrailsPrompt } from './04-guardrails.js';
// NOTE: 05-claude-code is excluded — Claude Code agents require serve() for the
// framework worker subprocess. run() does not spawn it.

// ── Config ──────────────────────────────────────────────

const TIMEOUT_MS = 30_000;

interface TestCase {
  name: string;
  agent: object;
  prompt: string;
  expectTools?: boolean;
  expectGuardrails?: boolean;
}

const tests: TestCase[] = [
  { name: '01-basic-agent', agent: basicAgent, prompt: basicPrompt },
  { name: '02-tools', agent: toolsAgent, prompt: toolsPrompt, expectTools: true },
  { name: '03-multi-agent', agent: multiAgent, prompt: multiPrompt },
  { name: '04-guardrails', agent: guardrailsAgent, prompt: guardrailsPrompt, expectGuardrails: true },
];

// ── Helpers ─────────────────────────────────────────────

const serverUrl = process.env.AGENTSPAN_SERVER_URL ?? 'http://localhost:6767/api';

async function fetchExecutionTasks(executionId: string): Promise<any> {
  const url = `${serverUrl}/agent/executions/${executionId}/full`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch execution ${executionId}: ${res.status}`);
  return res.json();
}

// System task types managed by Conductor/AgentSpan — everything else is a tool worker task
const SYSTEM_TASK_TYPES = new Set([
  'LLM_CHAT_COMPLETE', 'SET_VARIABLE', 'DO_WHILE', 'SWITCH', 'FORK', 'JOIN',
  'INLINE', 'SUB_WORKFLOW', 'HUMAN', 'TERMINATE', 'WAIT', 'EVENT',
  'JSON_JQ_TRANSFORM', 'KAFKA_PUBLISH', 'HTTP',
]);

function isToolTask(task: any): boolean {
  return !SYSTEM_TASK_TYPES.has(task.taskType);
}

function validateTasks(execution: any, testCase: TestCase): string[] {
  const errors: string[] = [];
  const tasks: any[] = execution.tasks ?? [];

  for (const task of tasks) {
    const taskName = task.referenceTaskName ?? task.taskType ?? 'unknown';
    const status = task.status;

    // Tool tasks: must not be COMPLETED_WITH_ERRORS or FAILED
    if (isToolTask(task)) {
      if (status === 'COMPLETED_WITH_ERRORS') {
        errors.push(`Tool task "${taskName}" completed with errors`);
      }
      if (status === 'FAILED' || status === 'FAILED_WITH_TERMINAL_ERROR') {
        errors.push(`Tool task "${taskName}" failed with status ${status}`);
      }
    }

    // SUB_WORKFLOW tasks (multi-agent)
    if (task.taskType === 'SUB_WORKFLOW') {
      if (status === 'FAILED' || status === 'COMPLETED_WITH_ERRORS') {
        errors.push(`Sub-workflow task "${taskName}" has status ${status}`);
      }
    }

    // Guardrail tasks
    if (taskName.toLowerCase().includes('guardrail') || task.taskType === 'INLINE') {
      if (status === 'FAILED' || status === 'COMPLETED_WITH_ERRORS') {
        errors.push(`Guardrail task "${taskName}" has status ${status}`);
      }
    }
  }

  // If we expected tools, verify at least one tool call exists
  if (testCase.expectTools) {
    const toolTasks = tasks.filter(isToolTask);
    if (toolTasks.length === 0) {
      errors.push('Expected tool calls but found none');
    }
  }

  return errors;
}

// ── Runner ──────────────────────────────────────────────

async function runTest(
  testCase: TestCase,
): Promise<{ name: string; passed: boolean; durationMs: number; errors: string[] }> {
  const start = Date.now();
  const errors: string[] = [];

  // Each test gets its own runtime so tool workers don't interfere
  const runtime = new AgentRuntime();

  try {
    // Use run() which handles worker lifecycle end-to-end
    let timer: ReturnType<typeof setTimeout>;
    const result = await Promise.race([
      runtime.run(testCase.agent, testCase.prompt),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`Timed out after ${TIMEOUT_MS}ms`)), TIMEOUT_MS);
      }),
    ]);
    clearTimeout(timer!);

    const durationMs = Date.now() - start;

    // (a) Must complete successfully
    if (!result.isSuccess) {
      errors.push(`Expected COMPLETED but got ${result.status}${result.error ? `: ${result.error}` : ''}`);
    }

    // (b) Must finish within 30 seconds
    if (durationMs > TIMEOUT_MS) {
      errors.push(`Took ${durationMs}ms (limit: ${TIMEOUT_MS}ms)`);
    }

    // (c) & (d) Validate individual task statuses
    try {
      const execution = await fetchExecutionTasks(result.executionId);
      const taskErrors = validateTasks(execution, testCase);
      errors.push(...taskErrors);
    } catch (e: any) {
      errors.push(`Failed to fetch execution details: ${e.message}`);
    }

    return { name: testCase.name, passed: errors.length === 0, durationMs, errors };
  } catch (e: any) {
    return {
      name: testCase.name,
      passed: false,
      durationMs: Date.now() - start,
      errors: [e.message],
    };
  } finally {
    await runtime.shutdown();
  }
}

// ── Main ────────────────────────────────────────────────

async function main() {
  console.log(`\nRunning ${tests.length} quickstart examples in parallel...\n`);

  // Start all tests in parallel — each with its own runtime
  const results = await Promise.all(tests.map((t) => runTest(t)));

  // Print results
  let allPassed = true;
  for (const r of results) {
    const icon = r.passed ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m';
    console.log(`  [${icon}] ${r.name} (${r.durationMs}ms)`);
    for (const err of r.errors) {
      console.log(`         -> ${err}`);
    }
    if (!r.passed) allPassed = false;
  }

  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;
  console.log(`\n${passed} passed, ${failed} failed out of ${results.length}\n`);

  if (!allPassed) {
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
