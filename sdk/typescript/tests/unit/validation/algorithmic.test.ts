import { describe, it, expect } from 'vitest';
import {
  runAlgorithmicChecks,
  determineStatus,
} from '../../../validation/checks/algorithmic.js';
import type { AgentEvent } from '../../../src/types.js';

describe('runAlgorithmicChecks', () => {
  it('returns all-green for a successful workflow with thinking and output', () => {
    const events: AgentEvent[] = [
      { type: 'thinking', content: 'Planning response...' },
      { type: 'message', content: 'Here is the answer.' },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: 'Here is the answer.',
      events,
    });

    expect(checks.workflowCompleted).toBe(true);
    expect(checks.noUnhandledErrors).toBe(true);
    expect(checks.allToolsSucceeded).toBe(true);
    expect(checks.llmEngaged).toBe(true);
    expect(checks.outputNonEmpty).toBe(true);
    expect(checks.toolAudit).toHaveLength(0);
  });

  it('marks workflowCompleted false when status is FAILED', () => {
    const checks = runAlgorithmicChecks({
      status: 'FAILED',
      output: '',
      events: [],
    });
    expect(checks.workflowCompleted).toBe(false);
  });

  it('marks llmEngaged true when completed with output (even without thinking events)', () => {
    const events: AgentEvent[] = [
      { type: 'message', content: 'hello' },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: 'hello',
      events,
    });
    // Completed with output implies LLM engagement
    expect(checks.llmEngaged).toBe(true);
  });

  it('marks llmEngaged false when completed but output is empty', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: '',
      events: [{ type: 'done' }],
    });
    expect(checks.llmEngaged).toBe(false);
  });

  it('relaxes llmEngaged for framework passthrough when workflow completed', () => {
    const events: AgentEvent[] = [
      { type: 'message', content: 'framework output' },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks(
      { status: 'COMPLETED', output: 'framework output', events },
      { isFrameworkPassthrough: true },
    );
    expect(checks.llmEngaged).toBe(true);
  });

  it('marks llmEngaged false for passthrough when workflow failed with no output', () => {
    const checks = runAlgorithmicChecks(
      { status: 'FAILED', output: '', events: [] },
      { isFrameworkPassthrough: true },
    );
    // Passthrough flag alone isn't enough — need completed status
    expect(checks.llmEngaged).toBe(false);
  });

  it('marks outputNonEmpty false for empty string output', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: '',
      events: [{ type: 'thinking', content: 'ok' }],
    });
    expect(checks.outputNonEmpty).toBe(false);
  });

  it('marks outputNonEmpty false for whitespace-only output', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: '   \n\t  ',
      events: [{ type: 'thinking', content: 'ok' }],
    });
    expect(checks.outputNonEmpty).toBe(false);
  });

  it('marks outputNonEmpty true for non-empty object output', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: { result: 'hello' },
      events: [{ type: 'thinking', content: 'ok' }],
    });
    expect(checks.outputNonEmpty).toBe(true);
  });

  it('marks outputNonEmpty false for null output', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: null,
      events: [{ type: 'thinking', content: 'ok' }],
    });
    expect(checks.outputNonEmpty).toBe(false);
  });

  it('marks outputNonEmpty false for empty object output', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: {},
      events: [{ type: 'thinking', content: 'ok' }],
    });
    expect(checks.outputNonEmpty).toBe(false);
  });

  it('marks outputNonEmpty false for { result: null } output', () => {
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: { result: null },
      events: [{ type: 'thinking', content: 'ok' }],
    });
    expect(checks.outputNonEmpty).toBe(false);
  });

  it('detects unhandled error events', () => {
    const events: AgentEvent[] = [
      { type: 'thinking', content: 'ok' },
      { type: 'error', content: 'something went wrong' },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: 'partial result',
      events,
    });
    expect(checks.noUnhandledErrors).toBe(false);
  });

  it('does not flag error followed by successful retry', () => {
    const events: AgentEvent[] = [
      { type: 'thinking', content: 'ok' },
      { type: 'error', content: 'tool failed', toolName: 'search' },
      { type: 'tool_result', toolName: 'search', result: { data: 'ok' } },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: 'result',
      events,
    });
    expect(checks.noUnhandledErrors).toBe(true);
  });

  it('runs tool audit on events with tool calls', () => {
    const events: AgentEvent[] = [
      { type: 'thinking', content: 'using tool' },
      { type: 'tool_call', toolName: 'calc', args: { x: 1 } },
      { type: 'tool_result', toolName: 'calc', result: { answer: 2 } },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: '2',
      events,
    });
    expect(checks.toolAudit).toHaveLength(1);
    expect(checks.toolAudit[0].succeeded).toBe(true);
    expect(checks.allToolsSucceeded).toBe(true);
  });

  it('marks allToolsSucceeded false when a tool fails permanently', () => {
    const events: AgentEvent[] = [
      { type: 'thinking', content: 'using tool' },
      { type: 'tool_call', toolName: 'api', args: {} },
      { type: 'tool_result', toolName: 'api', result: { error: 'not found' } },
      { type: 'done' },
    ];
    const checks = runAlgorithmicChecks({
      status: 'COMPLETED',
      output: 'fallback result',
      events,
    });
    expect(checks.allToolsSucceeded).toBe(false);
  });
});

describe('determineStatus', () => {
  const greenChecks = {
    workflowCompleted: true,
    noUnhandledErrors: true,
    toolAudit: [],
    allToolsSucceeded: true,
    llmEngaged: true,
    outputNonEmpty: true,
  };

  it('returns PASS when all checks green and no judge', () => {
    expect(determineStatus(greenChecks)).toBe('PASS');
  });

  it('returns PASS when all checks green and judge >= 3', () => {
    expect(determineStatus(greenChecks, 4)).toBe('PASS');
    expect(determineStatus(greenChecks, 3)).toBe('PASS');
    expect(determineStatus(greenChecks, 5)).toBe('PASS');
  });

  it('returns WARN when all checks green but judge < 3', () => {
    expect(determineStatus(greenChecks, 2)).toBe('WARN');
    expect(determineStatus(greenChecks, 1)).toBe('WARN');
  });

  it('returns FAIL when any check fails regardless of judge score', () => {
    expect(determineStatus({ ...greenChecks, workflowCompleted: false }, 5)).toBe('FAIL');
    expect(determineStatus({ ...greenChecks, noUnhandledErrors: false }, 5)).toBe('FAIL');
    expect(determineStatus({ ...greenChecks, allToolsSucceeded: false }, 5)).toBe('FAIL');
    expect(determineStatus({ ...greenChecks, llmEngaged: false }, 5)).toBe('FAIL');
    expect(determineStatus({ ...greenChecks, outputNonEmpty: false }, 5)).toBe('FAIL');
  });

  it('respects custom pass threshold', () => {
    expect(determineStatus(greenChecks, 3, 4)).toBe('WARN');
    expect(determineStatus(greenChecks, 4, 4)).toBe('PASS');
  });
});
