import type { AgentResult, AgentEvent, Status, FinishReason, TokenUsage } from './types.js';
import { normalizeOutput, createAgentResult } from './types.js';

// ── Runtime-accessible const objects ────────────────────

/**
 * Event types as a runtime-accessible const object.
 */
export const EventTypes = {
  THINKING: 'thinking',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  GUARDRAIL_PASS: 'guardrail_pass',
  GUARDRAIL_FAIL: 'guardrail_fail',
  WAITING: 'waiting',
  HANDOFF: 'handoff',
  MESSAGE: 'message',
  ERROR: 'error',
  DONE: 'done',
} as const;

/**
 * Terminal workflow statuses as a runtime-accessible const object.
 */
export const Statuses = {
  COMPLETED: 'COMPLETED',
  FAILED: 'FAILED',
  TERMINATED: 'TERMINATED',
  TIMED_OUT: 'TIMED_OUT',
} as const;

/**
 * Set of terminal workflow statuses.
 */
export const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  Statuses.COMPLETED,
  Statuses.FAILED,
  Statuses.TERMINATED,
  Statuses.TIMED_OUT,
]);

/**
 * Finish reasons as a runtime-accessible const object.
 */
export const FinishReasons = {
  STOP: 'stop',
  LENGTH: 'length',
  TOOL_CALLS: 'tool_calls',
  ERROR: 'error',
  CANCELLED: 'cancelled',
  TIMEOUT: 'timeout',
  GUARDRAIL: 'guardrail',
  REJECTED: 'rejected',
} as const;

// ── makeAgentResult factory ─────────────────────────────

export interface MakeAgentResultData {
  output?: unknown;
  executionId?: string;
  correlationId?: string;
  messages?: unknown[];
  toolCalls?: unknown[];
  status?: string;
  finishReason?: string;
  error?: string;
  errorMessage?: string;
  tokenUsage?: TokenUsage;
  metadata?: Record<string, unknown>;
  events?: AgentEvent[];
  subResults?: Record<string, unknown>;
}

/**
 * Factory function that creates an AgentResult with computed getters.
 *
 * Output normalization:
 * - string -> { result: string }
 * - null + COMPLETED -> { result: null }
 * - null + FAILED -> { error: errorMessage }
 * - object -> as-is
 */
export function makeAgentResult(data: MakeAgentResultData): AgentResult {
  const status = (data.status as Status) ?? 'FAILED';
  const finishReason = resolveFinishReason(data);
  const errorMessage = data.error ?? data.errorMessage;

  // Normalize output
  const output = normalizeOutput(data.output, status, errorMessage);

  return createAgentResult({
    output,
    executionId: data.executionId ?? '',
    correlationId: data.correlationId,
    messages: data.messages ?? [],
    toolCalls: data.toolCalls ?? [],
    status,
    finishReason,
    error: errorMessage,
    tokenUsage: data.tokenUsage,
    metadata: data.metadata,
    events: data.events ?? [],
    subResults: data.subResults,
  });
}

/**
 * Resolve FinishReason from data, inferring from status if not provided.
 */
function resolveFinishReason(data: MakeAgentResultData): FinishReason {
  if (data.finishReason) {
    return data.finishReason as FinishReason;
  }

  const status = data.status ?? 'FAILED';

  switch (status) {
    case 'COMPLETED':
      return 'stop';
    case 'FAILED':
      return 'error';
    case 'TERMINATED':
      return 'cancelled';
    case 'TIMED_OUT':
      return 'timeout';
    default:
      return 'error';
  }
}
