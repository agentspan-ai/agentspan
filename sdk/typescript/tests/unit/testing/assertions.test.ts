import { describe, it, expect } from 'vitest';
import {
  assertToolUsed,
  assertToolNotUsed,
  assertToolCalledWith,
  assertToolCallOrder,
  assertToolsUsedExactly,
  assertOutputContains,
  assertOutputMatches,
  assertOutputType,
  assertStatus,
  assertNoErrors,
  assertEventsContain,
  assertEventSequence,
  assertHandoffTo,
  assertAgentRan,
  assertGuardrailPassed,
  assertGuardrailFailed,
  assertMaxTurns,
} from '../../../src/testing/assertions.js';
import { makeAgentResult } from '../../../src/result.js';
import type { AgentEvent } from '../../../src/types.js';

// ── Helpers ──────────────────────────────────────────────

function makeResult(opts: {
  events?: AgentEvent[];
  status?: string;
  output?: unknown;
  toolCalls?: unknown[];
}) {
  return makeAgentResult({
    executionId: 'wf-test',
    status: opts.status ?? 'COMPLETED',
    events: opts.events ?? [],
    output: opts.output,
    toolCalls: opts.toolCalls,
  });
}

// ── Tool assertions ──────────────────────────────────────

describe('assertToolUsed', () => {
  it('passes when tool was used', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search', args: {} }],
    });
    expect(() => assertToolUsed(result, 'search')).not.toThrow();
  });

  it('throws when tool was not used', () => {
    const result = makeResult({ toolCalls: [] });
    expect(() => assertToolUsed(result, 'search')).toThrow(/search/);
  });
});

describe('assertToolNotUsed', () => {
  it('passes when tool was not used', () => {
    const result = makeResult({ toolCalls: [] });
    expect(() => assertToolNotUsed(result, 'search')).not.toThrow();
  });

  it('throws when tool was used', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search', args: {} }],
    });
    expect(() => assertToolNotUsed(result, 'search')).toThrow(/search/);
  });
});

describe('assertToolCalledWith', () => {
  it('passes with matching args (subset)', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search', args: { q: 'test', limit: 10 } }],
    });
    expect(() =>
      assertToolCalledWith(result, 'search', { q: 'test' }),
    ).not.toThrow();
  });

  it('throws when args do not match', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search', args: { q: 'other' } }],
    });
    expect(() =>
      assertToolCalledWith(result, 'search', { q: 'test' }),
    ).toThrow(/never with matching args/);
  });

  it('throws when tool not found', () => {
    const result = makeResult({ toolCalls: [] });
    expect(() =>
      assertToolCalledWith(result, 'search', { q: 'test' }),
    ).toThrow(/to be called, but it was not/);
  });

  it('passes when args is null', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search', args: {} }],
    });
    expect(() => assertToolCalledWith(result, 'search')).not.toThrow();
  });
});

describe('assertToolCallOrder', () => {
  it('passes when tools appear in subsequence order', () => {
    const result = makeResult({
      toolCalls: [
        { name: 'search' },
        { name: 'filter' },
        { name: 'format' },
      ],
    });
    expect(() =>
      assertToolCallOrder(result, ['search', 'format']),
    ).not.toThrow();
  });

  it('throws when order is violated', () => {
    const result = makeResult({
      toolCalls: [{ name: 'format' }, { name: 'search' }],
    });
    expect(() =>
      assertToolCallOrder(result, ['search', 'format']),
    ).toThrow(/only matched up to/);
  });
});

describe('assertToolsUsedExactly', () => {
  it('passes when exact set matches', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search' }, { name: 'format' }],
    });
    expect(() =>
      assertToolsUsedExactly(result, ['format', 'search']),
    ).not.toThrow();
  });

  it('throws when sets differ', () => {
    const result = makeResult({
      toolCalls: [{ name: 'search' }],
    });
    expect(() =>
      assertToolsUsedExactly(result, ['search', 'format']),
    ).toThrow(/missing/);
  });
});

// ── Output assertions ────────────────────────────────────

describe('assertOutputContains', () => {
  it('passes when output contains text', () => {
    const result = makeResult({ output: { result: 'Hello World' } });
    expect(() => assertOutputContains(result, 'Hello')).not.toThrow();
  });

  it('throws when output does not contain text', () => {
    const result = makeResult({ output: { result: 'Goodbye' } });
    expect(() => assertOutputContains(result, 'Hello')).toThrow(/Hello/);
  });

  it('respects caseSensitive flag', () => {
    const result = makeResult({ output: { result: 'Hello World' } });
    expect(() =>
      assertOutputContains(result, 'hello', { caseSensitive: false }),
    ).not.toThrow();
  });
});

describe('assertOutputMatches', () => {
  it('passes when pattern matches', () => {
    const result = makeResult({ output: { result: 'order #123' } });
    expect(() =>
      assertOutputMatches(result, /order #\d+/),
    ).not.toThrow();
  });

  it('throws when pattern does not match', () => {
    const result = makeResult({ output: { result: 'no numbers' } });
    expect(() => assertOutputMatches(result, /\d+/)).toThrow(/does not/);
  });

  it('accepts string pattern', () => {
    const result = makeResult({ output: { result: 'hello world' } });
    expect(() => assertOutputMatches(result, 'hello')).not.toThrow();
  });
});

describe('assertOutputType', () => {
  it('passes when type matches', () => {
    const result = makeResult({ output: { result: 'test' } });
    expect(() => assertOutputType(result, 'object')).not.toThrow();
  });

  it('throws when type does not match', () => {
    const result = makeResult({ output: { result: 'test' } });
    expect(() => assertOutputType(result, 'string')).toThrow(/object/);
  });
});

// ── Status assertions ────────────────────────────────────

describe('assertStatus', () => {
  it('passes when status matches', () => {
    const result = makeResult({ status: 'COMPLETED' });
    expect(() => assertStatus(result, 'COMPLETED')).not.toThrow();
  });

  it('throws when status does not match', () => {
    const result = makeResult({ status: 'COMPLETED' });
    expect(() => assertStatus(result, 'FAILED')).toThrow(/FAILED.*COMPLETED/);
  });
});

describe('assertNoErrors', () => {
  it('passes when no errors', () => {
    const result = makeResult({ events: [{ type: 'done' }] });
    expect(() => assertNoErrors(result)).not.toThrow();
  });

  it('throws when errors exist', () => {
    const result = makeResult({
      events: [{ type: 'error', content: 'boom' }],
    });
    expect(() => assertNoErrors(result)).toThrow(/1 error/);
  });
});

// ── Event assertions ─────────────────────────────────────

describe('assertEventsContain', () => {
  it('passes when event type exists', () => {
    const result = makeResult({
      events: [{ type: 'thinking', content: 'hmm' }],
    });
    expect(() => assertEventsContain(result, 'thinking')).not.toThrow();
  });

  it('throws when event type missing', () => {
    const result = makeResult({ events: [] });
    expect(() => assertEventsContain(result, 'thinking')).toThrow(
      /none found/,
    );
  });

  it('supports expected=false (negation)', () => {
    const result = makeResult({ events: [] });
    expect(() =>
      assertEventsContain(result, 'error', { expected: false }),
    ).not.toThrow();
  });

  it('throws on expected=false when event exists', () => {
    const result = makeResult({
      events: [{ type: 'error', content: 'x' }],
    });
    expect(() =>
      assertEventsContain(result, 'error', { expected: false }),
    ).toThrow(/NO event/);
  });
});

describe('assertEventSequence', () => {
  it('passes when types appear in subsequence', () => {
    const result = makeResult({
      events: [
        { type: 'thinking' },
        { type: 'tool_call', toolName: 'x' },
        { type: 'tool_result', toolName: 'x' },
        { type: 'done' },
      ],
    });
    expect(() =>
      assertEventSequence(result, ['thinking', 'tool_call', 'done']),
    ).not.toThrow();
  });

  it('throws when sequence not found', () => {
    const result = makeResult({
      events: [{ type: 'done' }, { type: 'thinking' }],
    });
    expect(() =>
      assertEventSequence(result, ['thinking', 'done']),
    ).toThrow(/only matched/);
  });
});

// ── Multi-agent assertions ───────────────────────────────

describe('assertHandoffTo', () => {
  it('passes when handoff event targets the agent', () => {
    const result = makeResult({
      events: [{ type: 'handoff', target: 'specialist' }],
    });
    expect(() => assertHandoffTo(result, 'specialist')).not.toThrow();
  });

  it('throws when no handoff to target', () => {
    const result = makeResult({ events: [] });
    expect(() => assertHandoffTo(result, 'specialist')).toThrow(
      /specialist/,
    );
  });
});

describe('assertAgentRan', () => {
  it('passes when handoff event targets agent (delegates to assertHandoffTo)', () => {
    const result = makeResult({
      events: [{ type: 'handoff', target: 'child' }],
    });
    expect(() => assertAgentRan(result, 'child')).not.toThrow();
  });

  it('throws when agent did not run', () => {
    const result = makeResult({ events: [] });
    expect(() => assertAgentRan(result, 'child')).toThrow(/child/);
  });
});

// ── Guardrail assertions ─────────────────────────────────

describe('assertGuardrailPassed', () => {
  it('passes when guardrail_pass event exists', () => {
    const result = makeResult({
      events: [{ type: 'guardrail_pass', guardrailName: 'no_pii' }],
    });
    expect(() => assertGuardrailPassed(result, 'no_pii')).not.toThrow();
  });

  it('throws when guardrail did not pass', () => {
    const result = makeResult({ events: [] });
    expect(() => assertGuardrailPassed(result, 'no_pii')).toThrow(/no_pii/);
  });
});

describe('assertGuardrailFailed', () => {
  it('passes when guardrail_fail event exists', () => {
    const result = makeResult({
      events: [{ type: 'guardrail_fail', guardrailName: 'no_pii' }],
    });
    expect(() => assertGuardrailFailed(result, 'no_pii')).not.toThrow();
  });

  it('throws when guardrail did not fail', () => {
    const result = makeResult({ events: [] });
    expect(() => assertGuardrailFailed(result, 'no_pii')).toThrow(/no_pii/);
  });
});

// ── Turn assertions ──────────────────────────────────────

describe('assertMaxTurns', () => {
  it('passes when turns are within limit', () => {
    const result = makeResult({
      events: [
        { type: 'tool_call', toolName: 'x' },
        { type: 'done' },
      ],
    });
    expect(() => assertMaxTurns(result, 5)).not.toThrow();
  });

  it('throws when turns exceed limit', () => {
    const result = makeResult({
      events: [
        { type: 'tool_call', toolName: 'a' },
        { type: 'tool_call', toolName: 'b' },
        { type: 'tool_call', toolName: 'c' },
        { type: 'done' },
      ],
    });
    expect(() => assertMaxTurns(result, 2)).toThrow(/4/);
  });
});
