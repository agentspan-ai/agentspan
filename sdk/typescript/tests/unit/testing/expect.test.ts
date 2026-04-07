import { describe, it, expect as vitestExpect } from 'vitest';
import {
  expect as agentExpect,
  AgentResultExpectation,
} from '../../../src/testing/expect.js';
import { makeAgentResult } from '../../../src/result.js';
import type { AgentEvent } from '../../../src/types.js';

// ── Helpers ──────────────────────────────────────────────

function completedResult(extras?: {
  events?: AgentEvent[];
  output?: unknown;
  toolCalls?: unknown[];
}) {
  return makeAgentResult({
    executionId: 'wf-test',
    status: 'COMPLETED',
    finishReason: 'stop',
    output: extras?.output ?? { result: 'done' },
    events: extras?.events ?? [],
    toolCalls: extras?.toolCalls,
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

describe('expect (fluent API)', () => {
  it('returns an AgentResultExpectation', () => {
    const e = agentExpect(completedResult());
    vitestExpect(e).toBeInstanceOf(AgentResultExpectation);
  });

  describe('completed / failed / status', () => {
    it('completed() passes for COMPLETED result', () => {
      vitestExpect(() =>
        agentExpect(completedResult()).completed(),
      ).not.toThrow();
    });

    it('completed() throws for FAILED result', () => {
      vitestExpect(() =>
        agentExpect(failedResult()).completed(),
      ).toThrow(/FAILED/);
    });

    it('failed() passes for FAILED result', () => {
      vitestExpect(() =>
        agentExpect(failedResult()).failed(),
      ).not.toThrow();
    });

    it('status() checks exact status', () => {
      vitestExpect(() =>
        agentExpect(completedResult()).status('COMPLETED'),
      ).not.toThrow();

      vitestExpect(() =>
        agentExpect(completedResult()).status('FAILED'),
      ).toThrow();
    });
  });

  describe('noErrors', () => {
    it('passes when no errors', () => {
      vitestExpect(() =>
        agentExpect(completedResult()).noErrors(),
      ).not.toThrow();
    });

    it('throws when error events exist', () => {
      const result = completedResult({
        events: [{ type: 'error', content: 'x' }],
      });
      vitestExpect(() => agentExpect(result).noErrors()).toThrow();
    });
  });

  describe('usedTool / didNotUseTool', () => {
    it('usedTool passes when tool was used', () => {
      const result = completedResult({
        toolCalls: [{ name: 'search', args: {} }],
      });
      vitestExpect(() =>
        agentExpect(result).usedTool('search'),
      ).not.toThrow();
    });

    it('usedTool with args checks args', () => {
      const result = completedResult({
        toolCalls: [{ name: 'search', args: { q: 'test' } }],
      });
      vitestExpect(() =>
        agentExpect(result).usedTool('search', { args: { q: 'test' } }),
      ).not.toThrow();
    });

    it('didNotUseTool passes when tool was not used', () => {
      const result = completedResult({ toolCalls: [] });
      vitestExpect(() =>
        agentExpect(result).didNotUseTool('search'),
      ).not.toThrow();
    });
  });

  describe('toolCallOrder / toolsUsedExactly', () => {
    it('toolCallOrder validates subsequence', () => {
      const result = completedResult({
        toolCalls: [
          { name: 'search' },
          { name: 'filter' },
          { name: 'format' },
        ],
      });
      vitestExpect(() =>
        agentExpect(result).toolCallOrder(['search', 'format']),
      ).not.toThrow();
    });

    it('toolsUsedExactly validates set equality', () => {
      const result = completedResult({
        toolCalls: [{ name: 'search' }, { name: 'format' }],
      });
      vitestExpect(() =>
        agentExpect(result).toolsUsedExactly(['format', 'search']),
      ).not.toThrow();
    });
  });

  describe('outputContains / outputMatches / outputType', () => {
    it('outputContains checks substring', () => {
      const result = completedResult({ output: { result: 'Hello World' } });
      vitestExpect(() =>
        agentExpect(result).outputContains('Hello'),
      ).not.toThrow();
    });

    it('outputMatches checks regex', () => {
      const result = completedResult({ output: { result: 'order #123' } });
      vitestExpect(() =>
        agentExpect(result).outputMatches(/order #\d+/),
      ).not.toThrow();
    });

    it('outputType checks typeof', () => {
      const result = completedResult({ output: { result: 'test' } });
      vitestExpect(() =>
        agentExpect(result).outputType('object'),
      ).not.toThrow();
    });
  });

  describe('eventsContain / eventSequence', () => {
    it('eventsContain checks event type existence', () => {
      const result = completedResult({
        events: [{ type: 'thinking', content: 'hmm' }],
      });
      vitestExpect(() =>
        agentExpect(result).eventsContain('thinking'),
      ).not.toThrow();
    });

    it('eventSequence checks subsequence', () => {
      const result = completedResult({
        events: [
          { type: 'thinking' },
          { type: 'tool_call', toolName: 'x' },
          { type: 'done' },
        ],
      });
      vitestExpect(() =>
        agentExpect(result).eventSequence(['thinking', 'done']),
      ).not.toThrow();
    });
  });

  describe('handoffTo / agentRan', () => {
    it('handoffTo checks handoff events', () => {
      const result = completedResult({
        events: [{ type: 'handoff', target: 'billing' }],
      });
      vitestExpect(() =>
        agentExpect(result).handoffTo('billing'),
      ).not.toThrow();
    });

    it('agentRan delegates to handoffTo', () => {
      const result = completedResult({
        events: [{ type: 'handoff', target: 'billing' }],
      });
      vitestExpect(() =>
        agentExpect(result).agentRan('billing'),
      ).not.toThrow();
    });
  });

  describe('guardrailPassed / guardrailFailed', () => {
    it('guardrailPassed checks guardrail_pass events', () => {
      const result = completedResult({
        events: [{ type: 'guardrail_pass', guardrailName: 'no_pii' }],
      });
      vitestExpect(() =>
        agentExpect(result).guardrailPassed('no_pii'),
      ).not.toThrow();
    });

    it('guardrailFailed checks guardrail_fail events', () => {
      const result = completedResult({
        events: [
          { type: 'guardrail_fail', guardrailName: 'policy', content: 'bad' },
        ],
      });
      vitestExpect(() =>
        agentExpect(result).guardrailFailed('policy'),
      ).not.toThrow();
    });
  });

  describe('maxTurns', () => {
    it('passes when within limit', () => {
      const result = completedResult({
        events: [{ type: 'tool_call', toolName: 'x' }, { type: 'done' }],
      });
      vitestExpect(() => agentExpect(result).maxTurns(5)).not.toThrow();
    });

    it('throws when exceeding limit', () => {
      const result = completedResult({
        events: [
          { type: 'tool_call', toolName: 'a' },
          { type: 'tool_call', toolName: 'b' },
          { type: 'tool_call', toolName: 'c' },
          { type: 'done' },
        ],
      });
      vitestExpect(() => agentExpect(result).maxTurns(2)).toThrow();
    });
  });

  describe('chaining', () => {
    it('supports chaining multiple assertions', () => {
      const result = completedResult({
        output: { result: 'Hello World' },
        toolCalls: [{ name: 'search', args: { q: 'test' } }],
        events: [
          { type: 'tool_call', toolName: 'search' },
          { type: 'guardrail_pass', guardrailName: 'safety' },
          { type: 'done' },
        ],
      });

      vitestExpect(() =>
        agentExpect(result)
          .completed()
          .noErrors()
          .usedTool('search')
          .outputContains('Hello')
          .guardrailPassed('safety')
          .maxTurns(10),
      ).not.toThrow();
    });

    it('throws on first failing assertion in chain', () => {
      vitestExpect(() =>
        agentExpect(failedResult())
          .completed()
          .noErrors(),
      ).toThrow();
    });
  });
});
