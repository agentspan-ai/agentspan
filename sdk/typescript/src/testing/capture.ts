// ── Eval case capture — auto-generate EvalCase from observed results ──

import type { AgentResult, AgentEvent } from '../types.js';
import type { Agent } from '../agent.js';
import type { EvalCase, Runtime } from './eval.js';

const INTERNAL_ARG_KEYS = new Set([
  '__agentspan_ctx__',
  '_agent_state',
  'method',
]);

function slugify(text: string, maxLen = 60): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, maxLen)
    .replace(/_$/, '');
}

function cleanArgs(
  args: Record<string, unknown>,
): Record<string, unknown> | null {
  const cleaned: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) {
    if (!INTERNAL_ARG_KEYS.has(k)) {
      cleaned[k] = v;
    }
  }
  return Object.keys(cleaned).length > 0 ? cleaned : null;
}

/**
 * Generate an EvalCase from an observed AgentResult.
 *
 * Inspects the result's tool calls, handoff events, status, and output
 * to build expectations automatically.
 */
export function evalCaseFromResult(
  result: AgentResult,
  opts: {
    agent: Agent;
    prompt: string;
    name?: string;
    includeToolArgs?: boolean;
    tags?: string[];
  },
): EvalCase {
  const {
    agent,
    prompt,
    name = slugify(prompt),
    includeToolArgs = true,
    tags = ['captured'],
  } = opts;

  // Extract tools used
  const toolNames: string[] = [];
  const toolArgs: Record<string, Record<string, unknown>> = {};

  for (const tc of result.toolCalls as Array<{
    name?: string;
    args?: Record<string, unknown>;
  }>) {
    const toolName = tc.name ?? '';
    if (toolName && !toolNames.includes(toolName)) {
      toolNames.push(toolName);
    }
    if (includeToolArgs && toolName && tc.args) {
      const cleaned = cleanArgs(tc.args);
      if (cleaned) {
        toolArgs[toolName] = cleaned;
      }
    }
  }

  // Extract handoff target
  let handoffTarget: string | undefined;
  for (const ev of result.events) {
    if (ev.type === 'handoff' && ev.target) {
      handoffTarget = ev.target;
      break;
    }
  }

  // Check for errors
  const hasErrors = result.events.some(
    (ev: AgentEvent) => ev.type === 'error',
  );

  return {
    name,
    agent,
    prompt,
    expectTools: toolNames.length > 0 ? toolNames : undefined,
    expectToolArgs:
      Object.keys(toolArgs).length > 0 ? toolArgs : undefined,
    expectHandoffTo: handoffTarget,
    expectStatus: result.status,
    expectNoErrors: !hasErrors,
    validateOrchestration: true,
    tags,
  };
}

/**
 * Run an agent and auto-generate an EvalCase from the result.
 *
 * Returns both the generated case and the original result for inspection.
 */
export async function captureEvalCase(
  runtime: Runtime,
  agent: Agent,
  prompt: string,
  opts?: {
    name?: string;
    includeToolArgs?: boolean;
    tags?: string[];
  },
): Promise<[EvalCase, AgentResult]> {
  const result = await runtime.run(agent, prompt);
  const evalCase = evalCaseFromResult(result, {
    agent,
    prompt,
    name: opts?.name,
    includeToolArgs: opts?.includeToolArgs,
    tags: opts?.tags,
  });
  return [evalCase, result];
}
