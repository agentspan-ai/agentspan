import { describe, it, expect, vi } from 'vitest';
import {
  makeAgentResult,
  EventTypes,
  Statuses,
  FinishReasons,
  TERMINAL_STATUSES,
} from '../../src/result.js';

// ── Runtime const objects ───────────────────────────────

describe('EventTypes', () => {
  it('has all expected event types', () => {
    expect(EventTypes.THINKING).toBe('thinking');
    expect(EventTypes.TOOL_CALL).toBe('tool_call');
    expect(EventTypes.TOOL_RESULT).toBe('tool_result');
    expect(EventTypes.GUARDRAIL_PASS).toBe('guardrail_pass');
    expect(EventTypes.GUARDRAIL_FAIL).toBe('guardrail_fail');
    expect(EventTypes.WAITING).toBe('waiting');
    expect(EventTypes.HANDOFF).toBe('handoff');
    expect(EventTypes.MESSAGE).toBe('message');
    expect(EventTypes.ERROR).toBe('error');
    expect(EventTypes.DONE).toBe('done');
  });
});

describe('Statuses', () => {
  it('has all terminal statuses', () => {
    expect(Statuses.COMPLETED).toBe('COMPLETED');
    expect(Statuses.FAILED).toBe('FAILED');
    expect(Statuses.TERMINATED).toBe('TERMINATED');
    expect(Statuses.TIMED_OUT).toBe('TIMED_OUT');
  });
});

describe('FinishReasons', () => {
  it('has all finish reasons', () => {
    expect(FinishReasons.STOP).toBe('stop');
    expect(FinishReasons.LENGTH).toBe('length');
    expect(FinishReasons.TOOL_CALLS).toBe('tool_calls');
    expect(FinishReasons.ERROR).toBe('error');
    expect(FinishReasons.CANCELLED).toBe('cancelled');
    expect(FinishReasons.TIMEOUT).toBe('timeout');
    expect(FinishReasons.GUARDRAIL).toBe('guardrail');
    expect(FinishReasons.REJECTED).toBe('rejected');
  });
});

describe('TERMINAL_STATUSES', () => {
  it('is a set of 4 terminal statuses', () => {
    expect(TERMINAL_STATUSES.size).toBe(4);
    expect(TERMINAL_STATUSES.has('COMPLETED')).toBe(true);
    expect(TERMINAL_STATUSES.has('FAILED')).toBe(true);
    expect(TERMINAL_STATUSES.has('TERMINATED')).toBe(true);
    expect(TERMINAL_STATUSES.has('TIMED_OUT')).toBe(true);
    expect(TERMINAL_STATUSES.has('RUNNING')).toBe(false);
  });
});

// ── makeAgentResult ─────────────────────────────────────

describe('makeAgentResult', () => {
  describe('output normalization', () => {
    it('normalizes string output to { result: string }', () => {
      const result = makeAgentResult({
        output: 'hello world',
        workflowId: 'wf-1',
        status: 'COMPLETED',
      });
      expect(result.output).toEqual({ result: 'hello world' });
    });

    it('normalizes null output + COMPLETED to { result: null }', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'COMPLETED',
      });
      expect(result.output).toEqual({ result: null });
    });

    it('normalizes null output + FAILED to { error: message }', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'FAILED',
        error: 'something went wrong',
      });
      expect(result.output).toEqual({ error: 'something went wrong' });
    });

    it('normalizes null output + FAILED with no error message', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'FAILED',
      });
      expect(result.output).toEqual({ error: 'Unknown error' });
    });

    it('passes object output as-is', () => {
      const result = makeAgentResult({
        output: { key: 'value', nested: { x: 1 } },
        workflowId: 'wf-1',
        status: 'COMPLETED',
      });
      expect(result.output).toEqual({ key: 'value', nested: { x: 1 } });
    });

    it('normalizes undefined output + COMPLETED', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        status: 'COMPLETED',
      });
      expect(result.output).toEqual({ result: null });
    });

    it('uses errorMessage field as fallback', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'FAILED',
        errorMessage: 'from errorMessage',
      });
      expect(result.output).toEqual({ error: 'from errorMessage' });
    });
  });

  describe('computed properties', () => {
    it('isSuccess is true for COMPLETED', () => {
      const result = makeAgentResult({
        output: 'ok',
        workflowId: 'wf-1',
        status: 'COMPLETED',
      });
      expect(result.isSuccess).toBe(true);
      expect(result.isFailed).toBe(false);
    });

    it('isFailed is true for FAILED', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'FAILED',
        error: 'err',
      });
      expect(result.isFailed).toBe(true);
      expect(result.isSuccess).toBe(false);
    });

    it('isFailed is true for TIMED_OUT', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'TIMED_OUT',
      });
      expect(result.isFailed).toBe(true);
      expect(result.isSuccess).toBe(false);
    });

    it('isRejected is true for rejected finishReason', () => {
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-1',
        status: 'FAILED',
        finishReason: 'rejected',
      });
      expect(result.isRejected).toBe(true);
    });

    it('isRejected is false for non-rejected finishReason', () => {
      const result = makeAgentResult({
        output: 'ok',
        workflowId: 'wf-1',
        status: 'COMPLETED',
        finishReason: 'stop',
      });
      expect(result.isRejected).toBe(false);
    });
  });

  describe('finish reason inference', () => {
    it('infers stop for COMPLETED', () => {
      const result = makeAgentResult({
        output: 'ok',
        workflowId: 'wf-1',
        status: 'COMPLETED',
      });
      expect(result.finishReason).toBe('stop');
    });

    it('infers error for FAILED', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        status: 'FAILED',
      });
      expect(result.finishReason).toBe('error');
    });

    it('infers cancelled for TERMINATED', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        status: 'TERMINATED',
      });
      expect(result.finishReason).toBe('cancelled');
    });

    it('infers timeout for TIMED_OUT', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        status: 'TIMED_OUT',
      });
      expect(result.finishReason).toBe('timeout');
    });

    it('uses explicit finishReason when provided', () => {
      const result = makeAgentResult({
        output: 'ok',
        workflowId: 'wf-1',
        status: 'COMPLETED',
        finishReason: 'length',
      });
      expect(result.finishReason).toBe('length');
    });
  });

  describe('default fields', () => {
    it('defaults messages to empty array', () => {
      const result = makeAgentResult({ workflowId: 'wf-1', status: 'COMPLETED' });
      expect(result.messages).toEqual([]);
    });

    it('defaults toolCalls to empty array', () => {
      const result = makeAgentResult({ workflowId: 'wf-1', status: 'COMPLETED' });
      expect(result.toolCalls).toEqual([]);
    });

    it('defaults events to empty array', () => {
      const result = makeAgentResult({ workflowId: 'wf-1', status: 'COMPLETED' });
      expect(result.events).toEqual([]);
    });

    it('defaults workflowId to empty string', () => {
      const result = makeAgentResult({ status: 'COMPLETED' });
      expect(result.workflowId).toBe('');
    });

    it('defaults status to FAILED', () => {
      const result = makeAgentResult({});
      expect(result.status).toBe('FAILED');
    });
  });

  describe('printResult', () => {
    it('prints to console without error', () => {
      const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
      const result = makeAgentResult({
        output: { answer: 42 },
        workflowId: 'wf-1',
        status: 'COMPLETED',
        tokenUsage: {
          promptTokens: 100,
          completionTokens: 50,
          totalTokens: 150,
        },
      });

      result.printResult();

      expect(spy).toHaveBeenCalled();
      const allOutput = spy.mock.calls.map((c) => c.join(' ')).join('\n');
      expect(allOutput).toContain('[OK]');
      expect(allOutput).toContain('wf-1');
      expect(allOutput).toContain('COMPLETED');
      spy.mockRestore();
    });

    it('prints failure status', () => {
      const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
      const result = makeAgentResult({
        output: null,
        workflowId: 'wf-2',
        status: 'FAILED',
        error: 'timeout exceeded',
      });

      result.printResult();

      const allOutput = spy.mock.calls.map((c) => c.join(' ')).join('\n');
      expect(allOutput).toContain('[FAIL]');
      expect(allOutput).toContain('timeout exceeded');
      spy.mockRestore();
    });
  });

  describe('metadata and sub-results', () => {
    it('carries correlationId', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        correlationId: 'corr-123',
        status: 'COMPLETED',
      });
      expect(result.correlationId).toBe('corr-123');
    });

    it('carries metadata', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        status: 'COMPLETED',
        metadata: { source: 'test' },
      });
      expect(result.metadata).toEqual({ source: 'test' });
    });

    it('carries subResults', () => {
      const result = makeAgentResult({
        workflowId: 'wf-1',
        status: 'COMPLETED',
        subResults: { child_agent: { result: 'done' } },
      });
      expect(result.subResults).toEqual({ child_agent: { result: 'done' } });
    });
  });
});
