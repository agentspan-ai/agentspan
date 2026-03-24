import type { AgentResult } from '../types.js';

/**
 * Fluent assertion interface returned by expectResult().
 * Each method returns `this` for chaining.
 */
export interface ResultExpectation {
  toBeCompleted(): ResultExpectation;
  toBeFailed(): ResultExpectation;
  toContainOutput(text: string): ResultExpectation;
  toHaveUsedTool(toolName: string): ResultExpectation;
  toHavePassedGuardrail(name: string): ResultExpectation;
  toHaveFinishReason(reason: string): ResultExpectation;
  toHaveTokenUsageBelow(max: number): ResultExpectation;
}

/**
 * Create a fluent assertion chain for an AgentResult.
 *
 * ```ts
 * expectResult(result)
 *   .toBeCompleted()
 *   .toHaveUsedTool('search')
 *   .toContainOutput('answer');
 * ```
 */
export function expectResult(result: AgentResult): ResultExpectation {
  const chain: ResultExpectation = {
    toBeCompleted() {
      if (result.status !== 'COMPLETED') {
        throw new Error(
          `Expected COMPLETED, got ${result.status}: ${result.error}`,
        );
      }
      return chain;
    },

    toBeFailed() {
      if (result.status === 'COMPLETED') {
        throw new Error('Expected failed status');
      }
      return chain;
    },

    toContainOutput(text: string) {
      if (!JSON.stringify(result.output).includes(text)) {
        throw new Error(`Output does not contain "${text}"`);
      }
      return chain;
    },

    toHaveUsedTool(toolName: string) {
      if (
        !result.events.some(
          (e) => e.type === 'tool_call' && e.toolName === toolName,
        )
      ) {
        throw new Error(`Tool "${toolName}" was not used`);
      }
      return chain;
    },

    toHavePassedGuardrail(name: string) {
      if (
        !result.events.some(
          (e) => e.type === 'guardrail_pass' && e.guardrailName === name,
        )
      ) {
        throw new Error(`Guardrail "${name}" did not pass`);
      }
      return chain;
    },

    toHaveFinishReason(reason: string) {
      if (result.finishReason !== reason) {
        throw new Error(
          `Expected finish reason "${reason}", got "${result.finishReason}"`,
        );
      }
      return chain;
    },

    toHaveTokenUsageBelow(max: number) {
      if (result.tokenUsage && result.tokenUsage.totalTokens > max) {
        throw new Error(
          `Token usage ${result.tokenUsage.totalTokens} exceeds ${max}`,
        );
      }
      return chain;
    },
  };

  return chain;
}
