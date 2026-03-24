/**
 * Algorithmic checks for validation.
 *
 * Runs deterministic checks on execution results:
 * - Workflow completed successfully
 * - No unhandled errors
 * - Tool audit (all tool_calls have successful tool_results)
 * - LLM engaged (thinking events present)
 * - Output non-empty
 */

import type { AgentEvent } from '../../src/types.js';
import { auditToolEvents, type ToolAuditEntry } from './event-audit.js';

export interface AlgorithmicChecks {
  workflowCompleted: boolean;
  noUnhandledErrors: boolean;
  toolAudit: ToolAuditEntry[];
  allToolsSucceeded: boolean;
  llmEngaged: boolean;
  outputNonEmpty: boolean;
}

/**
 * Check if an error event is followed by a successful retry of the same operation.
 */
function isFollowedByRetrySuccess(errorEvent: AgentEvent, events: AgentEvent[]): boolean {
  const errorIndex = events.indexOf(errorEvent);
  if (errorIndex === -1) return false;

  // Look for a subsequent non-error event of similar type
  for (let i = errorIndex + 1; i < events.length; i++) {
    const e = events[i];
    // If the same tool was retried and succeeded
    if (
      errorEvent.toolName &&
      e.type === 'tool_result' &&
      e.toolName === errorEvent.toolName
    ) {
      const result = e.result;
      if (result && typeof result === 'object') {
        const r = result as Record<string, unknown>;
        if (!r.error && !r.isError) return true;
      }
      // If content doesn't look like an error, it's a success
      if (typeof e.content === 'string') {
        const lower = e.content.toLowerCase();
        if (!lower.includes('error') && !lower.includes('exception')) return true;
      }
      return true;
    }
  }
  return false;
}

/**
 * Run all algorithmic checks on an execution result.
 *
 * @param result - The execution result with status, output, and events
 * @param options - Options to relax certain checks
 * @param options.isFrameworkPassthrough - If true, relax llmEngaged to just workflowCompleted
 */
export function runAlgorithmicChecks(
  result: { status: string; output: unknown; events: AgentEvent[] },
  options?: { isFrameworkPassthrough?: boolean },
): AlgorithmicChecks {
  const { status, output, events } = result;

  // 1. Workflow completed
  const workflowCompleted = status === 'COMPLETED';

  // 2. No unhandled errors
  const noUnhandledErrors = !events.some(
    (e) => e.type === 'error' && !isFollowedByRetrySuccess(e, events),
  );

  // 3. Tool audit
  const toolAudit = auditToolEvents(events);
  const allToolsSucceeded = toolAudit.every(
    (t) => t.succeeded || t.retriedAndFixed,
  );

  // 5. Output non-empty (computed before LLM check since it depends on it)
  let outputNonEmpty = false;
  let outputStr = '';
  if (output != null) {
    if (typeof output === 'string') {
      outputStr = output.trim();
      outputNonEmpty = outputStr.length > 0;
    } else if (typeof output === 'object') {
      outputStr = JSON.stringify(output);
      outputNonEmpty = outputStr !== '{}' && outputStr !== '{"result":null}' && outputStr.length > 2;
    } else {
      outputStr = String(output);
      outputNonEmpty = true;
    }
  }

  // 4. LLM engaged
  // Framework passthrough and non-streaming examples may not emit thinking events.
  // If the workflow completed with output, the LLM was engaged (it produced the output).
  const hasThinkingEvents = events.some((e) => e.type === 'thinking');
  const llmEngaged = hasThinkingEvents
    || (options?.isFrameworkPassthrough === true && workflowCompleted)
    || (workflowCompleted && outputNonEmpty);

  return {
    workflowCompleted,
    noUnhandledErrors,
    toolAudit,
    allToolsSucceeded,
    llmEngaged,
    outputNonEmpty,
  };
}

/**
 * Determine overall validation status from algorithmic checks and judge score.
 *
 * PASS = allAlgorithmicChecksGreen && judgeScore >= 3
 * WARN = allAlgorithmicChecksGreen && judgeScore < 3
 * FAIL = anyAlgorithmicCheckFailed (regardless of judge score)
 */
export function determineStatus(
  checks: AlgorithmicChecks,
  judgeScore?: number,
  passThreshold = 3,
): 'PASS' | 'FAIL' | 'WARN' {
  const allGreen =
    checks.workflowCompleted &&
    checks.noUnhandledErrors &&
    checks.allToolsSucceeded &&
    checks.llmEngaged &&
    checks.outputNonEmpty;

  if (!allGreen) return 'FAIL';
  if (judgeScore !== undefined && judgeScore < passThreshold) return 'WARN';
  return 'PASS';
}
