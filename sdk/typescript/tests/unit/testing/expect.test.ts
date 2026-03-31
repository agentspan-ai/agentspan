import { describe, it, expect } from 'vitest';
import { expectResult } from '../../../src/testing/expect.js';
import { makeAgentResult } from '../../../src/result.js';
import type { AgentEvent } from '../../../src/types.js';

// ── Helpers ──────────────────────────────────────────────

function completedResult(extras?: {
  events?: AgentEvent[];
  output?: Record<string, unknown>;
  tokenUsage?: { promptTokens: number; completionTokens: number; totalTokens: number };
}) {
  return makeAgentResult({
    executionId: 'wf-test',
    status: 'COMPLETED',
    finishReason: 'stop',
    output: extras?.output ?? { result: 'done' },
    events: extras?.events ?? [],
    tokenUsage: extras?.tokenUsage,
  });
}

function failedResult(error?: string) {
  return makeAgentResult({
    executionId: 'wf-test',
    status: 'FAILED',
    finishReason: 'error',
    error: error ?? 'something went wrong',
  });
}

// ── Tests ────────────────────────────────────────────────

describe('expectResult', () => {
  describe('toBeCompleted', () => {
    it('passes for COMPLETED result', () => {
      expect(() => expectResult(completedResult()).toBeCompleted()).not.toThrow();
    });

    it('throws for FAILED result', () => {
      expect(() => expectResult(failedResult()).toBeCompleted()).toThrow(
        /Expected COMPLETED, got FAILED/,
      );
    });

    it('includes error message in thrown error', () => {
      expect(() =>
        expectResult(failedResult('timeout')).toBeCompleted(),
      ).toThrow(/timeout/);
    });
  });

  describe('toBeFailed', () => {
    it('passes for FAILED result', () => {
      expect(() => expectResult(failedResult()).toBeFailed()).not.toThrow();
    });

    it('throws for COMPLETED result', () => {
      expect(() => expectResult(completedResult()).toBeFailed()).toThrow(
        /Expected failed status/,
      );
    });
  });

  describe('toContainOutput', () => {
    it('passes when output contains text', () => {
      const result = completedResult({ output: { result: 'Hello World' } });
      expect(() => expectResult(result).toContainOutput('Hello')).not.toThrow();
    });

    it('throws when output does not contain text', () => {
      const result = completedResult({ output: { result: 'Goodbye' } });
      expect(() => expectResult(result).toContainOutput('Hello')).toThrow(
        /Output does not contain "Hello"/,
      );
    });
  });

  describe('toHaveUsedTool', () => {
    it('passes when tool_call event exists', () => {
      const result = completedResult({
        events: [{ type: 'tool_call', toolName: 'search' }],
      });
      expect(() =>
        expectResult(result).toHaveUsedTool('search'),
      ).not.toThrow();
    });

    it('throws when tool was not used', () => {
      const result = completedResult({ events: [] });
      expect(() => expectResult(result).toHaveUsedTool('search')).toThrow(
        /Tool "search" was not used/,
      );
    });

    it('throws when different tool was used', () => {
      const result = completedResult({
        events: [{ type: 'tool_call', toolName: 'fetch' }],
      });
      expect(() => expectResult(result).toHaveUsedTool('search')).toThrow(
        /Tool "search" was not used/,
      );
    });
  });

  describe('toHavePassedGuardrail', () => {
    it('passes when guardrail_pass event exists', () => {
      const result = completedResult({
        events: [{ type: 'guardrail_pass', guardrailName: 'no_pii' }],
      });
      expect(() =>
        expectResult(result).toHavePassedGuardrail('no_pii'),
      ).not.toThrow();
    });

    it('throws when guardrail did not pass', () => {
      const result = completedResult({ events: [] });
      expect(() =>
        expectResult(result).toHavePassedGuardrail('no_pii'),
      ).toThrow(/Guardrail "no_pii" did not pass/);
    });
  });

  describe('toHaveFinishReason', () => {
    it('passes when finish reason matches', () => {
      expect(() =>
        expectResult(completedResult()).toHaveFinishReason('stop'),
      ).not.toThrow();
    });

    it('throws when finish reason does not match', () => {
      expect(() =>
        expectResult(completedResult()).toHaveFinishReason('error'),
      ).toThrow(/Expected finish reason "error", got "stop"/);
    });
  });

  describe('toHaveTokenUsageBelow', () => {
    it('passes when token usage is below max', () => {
      const result = completedResult({
        tokenUsage: { promptTokens: 50, completionTokens: 30, totalTokens: 80 },
      });
      expect(() =>
        expectResult(result).toHaveTokenUsageBelow(100),
      ).not.toThrow();
    });

    it('throws when token usage exceeds max', () => {
      const result = completedResult({
        tokenUsage: {
          promptTokens: 100,
          completionTokens: 200,
          totalTokens: 300,
        },
      });
      expect(() =>
        expectResult(result).toHaveTokenUsageBelow(250),
      ).toThrow(/Token usage 300 exceeds 250/);
    });

    it('passes when no token usage is set (no usage to exceed)', () => {
      const result = completedResult();
      expect(() =>
        expectResult(result).toHaveTokenUsageBelow(100),
      ).not.toThrow();
    });
  });

  describe('chaining', () => {
    it('supports chaining multiple assertions', () => {
      const result = completedResult({
        output: { result: 'Hello World' },
        events: [
          { type: 'tool_call', toolName: 'search' },
          { type: 'guardrail_pass', guardrailName: 'safety' },
        ],
      });

      expect(() =>
        expectResult(result)
          .toBeCompleted()
          .toContainOutput('Hello')
          .toHaveUsedTool('search')
          .toHavePassedGuardrail('safety')
          .toHaveFinishReason('stop'),
      ).not.toThrow();
    });

    it('throws on first failing assertion in chain', () => {
      const result = failedResult();

      expect(() =>
        expectResult(result)
          .toBeCompleted() // This should throw
          .toContainOutput('test'),
      ).toThrow(/Expected COMPLETED/);
    });
  });
});
