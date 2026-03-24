import { describe, it, expect } from 'vitest';
import {
  assertToolUsed,
  assertGuardrailPassed,
  assertAgentRan,
  assertHandoffTo,
  assertStatus,
  assertNoErrors,
} from '../../../src/testing/assertions.js';
import { makeAgentResult } from '../../../src/result.js';
import type { AgentEvent } from '../../../src/types.js';

// ── Helpers ──────────────────────────────────────────────

function makeResult(opts: {
  events?: AgentEvent[];
  status?: string;
  subResults?: Record<string, unknown>;
}) {
  return makeAgentResult({
    workflowId: 'wf-test',
    status: opts.status ?? 'COMPLETED',
    events: opts.events ?? [],
    subResults: opts.subResults,
  });
}

// ── assertToolUsed ───────────────────────────────────────

describe('assertToolUsed', () => {
  it('passes when tool_call event exists for the tool', () => {
    const result = makeResult({
      events: [{ type: 'tool_call', toolName: 'search' }],
    });
    expect(() => assertToolUsed(result, 'search')).not.toThrow();
  });

  it('throws when tool was not used', () => {
    const result = makeResult({ events: [] });
    expect(() => assertToolUsed(result, 'search')).toThrow(
      /Expected tool "search" to have been used/,
    );
  });

  it('throws when a different tool was used', () => {
    const result = makeResult({
      events: [{ type: 'tool_call', toolName: 'fetch' }],
    });
    expect(() => assertToolUsed(result, 'search')).toThrow(
      /Expected tool "search" to have been used/,
    );
  });
});

// ── assertGuardrailPassed ────────────────────────────────

describe('assertGuardrailPassed', () => {
  it('passes when guardrail_pass event exists', () => {
    const result = makeResult({
      events: [{ type: 'guardrail_pass', guardrailName: 'no_pii' }],
    });
    expect(() => assertGuardrailPassed(result, 'no_pii')).not.toThrow();
  });

  it('throws when guardrail did not pass', () => {
    const result = makeResult({ events: [] });
    expect(() => assertGuardrailPassed(result, 'no_pii')).toThrow(
      /Expected guardrail "no_pii" to have passed/,
    );
  });
});

// ── assertAgentRan ───────────────────────────────────────

describe('assertAgentRan', () => {
  it('passes when agent is in subResults', () => {
    const result = makeResult({
      subResults: { child_agent: { result: 'done' } },
    });
    expect(() => assertAgentRan(result, 'child_agent')).not.toThrow();
  });

  it('passes when done event mentions agent name', () => {
    const result = makeResult({
      events: [
        {
          type: 'done',
          output: { result: 'Mock execution of child_agent' },
        },
      ],
    });
    expect(() => assertAgentRan(result, 'child_agent')).not.toThrow();
  });

  it('passes when handoff event targets agent', () => {
    const result = makeResult({
      events: [{ type: 'handoff', target: 'child_agent' }],
    });
    expect(() => assertAgentRan(result, 'child_agent')).not.toThrow();
  });

  it('throws when agent did not run', () => {
    const result = makeResult({ events: [] });
    expect(() => assertAgentRan(result, 'child_agent')).toThrow(
      /Expected agent "child_agent" to have run/,
    );
  });
});

// ── assertHandoffTo ──────────────────────────────────────

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
      /Expected handoff to "specialist"/,
    );
  });

  it('throws when handoff to different target', () => {
    const result = makeResult({
      events: [{ type: 'handoff', target: 'other' }],
    });
    expect(() => assertHandoffTo(result, 'specialist')).toThrow(
      /Expected handoff to "specialist"/,
    );
  });
});

// ── assertStatus ─────────────────────────────────────────

describe('assertStatus', () => {
  it('passes when status matches', () => {
    const result = makeResult({ status: 'COMPLETED' });
    expect(() => assertStatus(result, 'COMPLETED')).not.toThrow();
  });

  it('throws when status does not match', () => {
    const result = makeResult({ status: 'COMPLETED' });
    expect(() => assertStatus(result, 'FAILED')).toThrow(
      /Expected status "FAILED", got "COMPLETED"/,
    );
  });

  it('works for FAILED status', () => {
    const result = makeResult({ status: 'FAILED' });
    expect(() => assertStatus(result, 'FAILED')).not.toThrow();
  });

  it('works for TIMED_OUT status', () => {
    const result = makeResult({ status: 'TIMED_OUT' });
    expect(() => assertStatus(result, 'TIMED_OUT')).not.toThrow();
  });
});

// ── assertNoErrors ───────────────────────────────────────

describe('assertNoErrors', () => {
  it('passes when no error events exist', () => {
    const result = makeResult({
      events: [
        { type: 'tool_call', toolName: 'search' },
        { type: 'done' },
      ],
    });
    expect(() => assertNoErrors(result)).not.toThrow();
  });

  it('passes for empty events', () => {
    const result = makeResult({ events: [] });
    expect(() => assertNoErrors(result)).not.toThrow();
  });

  it('throws when error events exist', () => {
    const result = makeResult({
      events: [{ type: 'error', content: 'something broke' }],
    });
    expect(() => assertNoErrors(result)).toThrow(
      /Expected no errors, but found 1/,
    );
  });

  it('includes error content in message', () => {
    const result = makeResult({
      events: [{ type: 'error', content: 'disk full' }],
    });
    expect(() => assertNoErrors(result)).toThrow(/disk full/);
  });

  it('reports count of multiple errors', () => {
    const result = makeResult({
      events: [
        { type: 'error', content: 'err1' },
        { type: 'error', content: 'err2' },
      ],
    });
    expect(() => assertNoErrors(result)).toThrow(
      /Expected no errors, but found 2/,
    );
  });
});
