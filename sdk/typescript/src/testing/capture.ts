import type { AgentResult, AgentEvent, Status } from '../types.js';
import type { Agent } from '../agent.js';
import { mockRun } from './mock.js';
import type { MockRunOptions } from './mock.js';

/**
 * Internal keys injected by the runtime that should not appear in
 * captured tool arg expectations.
 */
const INTERNAL_ARG_KEYS = new Set([
  '__agentspan_ctx__',
  '_agent_state',
  'method',
]);

/**
 * An auto-generated eval case built from observed agent behavior.
 *
 * Use {@link evalCaseFromResult} or {@link captureEvalCase} to create one.
 */
export interface CapturedEvalCase {
  /** Descriptive name (auto-generated from prompt if not provided). */
  name: string;
  /** The prompt that was sent to the agent. */
  prompt: string;
  /** Tools that were called. */
  expectTools: string[] | null;
  /** Tool arguments observed (internal runtime keys stripped). */
  expectToolArgs: Record<string, Record<string, unknown>> | null;
  /** Agent name that received the handoff (if any). */
  expectHandoffTo: string | null;
  /** Expected terminal status. */
  expectStatus: Status;
  /** Whether the run had zero error events. */
  expectNoErrors: boolean;
  /** Tags for filtering. */
  tags: string[];
}

/**
 * Turn a prompt into a slug suitable for a test name.
 */
function slugify(text: string, maxLen = 60): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, maxLen)
    .replace(/_$/, '');
}

/**
 * Strip runtime-internal keys from a tool args object.
 */
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
 * Generate a {@link CapturedEvalCase} from an observed {@link AgentResult}.
 *
 * Inspects the result's tool calls, handoff events, and status to build
 * expectations automatically — no manual case authoring needed.
 *
 * @example
 * ```ts
 * const result = await runtime.run(agent, "What's the weather in Tokyo?");
 * const evalCase = evalCaseFromResult(result, {
 *   prompt: "What's the weather in Tokyo?",
 * });
 * // evalCase.expectTools === ["get_weather"]
 * // evalCase.expectToolArgs === { get_weather: { city: "Tokyo" } }
 * ```
 */
export function evalCaseFromResult(
  result: AgentResult,
  options: {
    prompt: string;
    name?: string;
    includeToolArgs?: boolean;
    tags?: string[];
  },
): CapturedEvalCase {
  const {
    prompt,
    name = slugify(prompt),
    includeToolArgs = true,
    tags = ['captured'],
  } = options;

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

  // Extract handoff target from events
  let handoffTarget: string | null = null;
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
    prompt,
    expectTools: toolNames.length > 0 ? toolNames : null,
    expectToolArgs: Object.keys(toolArgs).length > 0 ? toolArgs : null,
    expectHandoffTo: handoffTarget,
    expectStatus: result.status,
    expectNoErrors: !hasErrors,
    tags,
  };
}

/**
 * Run an agent via {@link mockRun} and auto-generate a
 * {@link CapturedEvalCase} from the observed behavior.
 *
 * Returns both the generated case and the original result for inspection.
 *
 * @example
 * ```ts
 * const [evalCase, result] = await captureEvalCase(
 *   agent,
 *   "Check stock for AAPL",
 * );
 * // evalCase is ready to use as a regression baseline
 * ```
 */
export async function captureEvalCase(
  agent: Agent,
  prompt: string,
  options?: MockRunOptions & {
    name?: string;
    includeToolArgs?: boolean;
    tags?: string[];
  },
): Promise<[CapturedEvalCase, AgentResult]> {
  const result = await mockRun(agent, prompt, options);
  const evalCase = evalCaseFromResult(result, {
    prompt,
    name: options?.name,
    includeToolArgs: options?.includeToolArgs,
    tags: options?.tags,
  });
  return [evalCase, result];
}
