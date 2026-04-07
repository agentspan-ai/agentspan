import { describe, it, expect } from 'vitest';
import { MockEvent, mockRun } from '../../../src/testing/mock.js';
import { Agent } from '../../../src/agent.js';

describe('MockEvent', () => {
  it('creates a thinking event', () => {
    const ev = MockEvent.thinking('hmm...');
    expect(ev.type).toBe('thinking');
    expect(ev.content).toBe('hmm...');
  });

  it('creates a tool_call event', () => {
    const ev = MockEvent.toolCall('search', { query: 'test' });
    expect(ev.type).toBe('tool_call');
    expect(ev.toolName).toBe('search');
    expect(ev.args).toEqual({ query: 'test' });
  });

  it('creates a tool_call event with default empty args', () => {
    const ev = MockEvent.toolCall('search');
    expect(ev.args).toEqual({});
  });

  it('creates a tool_result event', () => {
    const ev = MockEvent.toolResult('search', [{ title: 'result' }]);
    expect(ev.type).toBe('tool_result');
    expect(ev.toolName).toBe('search');
    expect(ev.result).toEqual([{ title: 'result' }]);
  });

  it('creates a handoff event', () => {
    const ev = MockEvent.handoff('specialist');
    expect(ev.type).toBe('handoff');
    expect(ev.target).toBe('specialist');
  });

  it('creates a message event', () => {
    const ev = MockEvent.message('hello');
    expect(ev.type).toBe('message');
    expect(ev.content).toBe('hello');
  });

  it('creates a guardrail_pass event', () => {
    const ev = MockEvent.guardrailPass('no_pii', 'clean');
    expect(ev.type).toBe('guardrail_pass');
    expect(ev.guardrailName).toBe('no_pii');
    expect(ev.content).toBe('clean');
  });

  it('creates a guardrail_fail event', () => {
    const ev = MockEvent.guardrailFail('no_pii', 'PII detected');
    expect(ev.type).toBe('guardrail_fail');
    expect(ev.guardrailName).toBe('no_pii');
    expect(ev.content).toBe('PII detected');
  });

  it('creates a waiting event', () => {
    const ev = MockEvent.waiting('awaiting input');
    expect(ev.type).toBe('waiting');
    expect(ev.content).toBe('awaiting input');
  });

  it('creates a done event', () => {
    const ev = MockEvent.done({ answer: 42 });
    expect(ev.type).toBe('done');
    expect(ev.output).toEqual({ answer: 42 });
  });

  it('creates an error event', () => {
    const ev = MockEvent.error('something broke');
    expect(ev.type).toBe('error');
    expect(ev.content).toBe('something broke');
  });
});

describe('mockRun', () => {
  it('builds AgentResult from scripted events', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'Hello', {
      events: [
        MockEvent.thinking('processing...'),
        MockEvent.done('Hello back!'),
      ],
    });

    expect(result.status).toBe('COMPLETED');
    expect(result.output).toEqual({ result: 'Hello back!' });
    expect(result.executionId).toBe('mock');
    expect(result.events).toHaveLength(2);
  });

  it('collects tool calls from events', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'search', {
      events: [
        MockEvent.toolCall('search', { query: 'test' }),
        MockEvent.toolResult('search', ['result1']),
        MockEvent.done('found it'),
      ],
    });

    expect(result.toolCalls).toHaveLength(1);
    const tc = result.toolCalls[0] as {
      name: string;
      args: unknown;
      result: unknown;
    };
    expect(tc.name).toBe('search');
    expect(tc.args).toEqual({ query: 'test' });
    expect(tc.result).toEqual(['result1']);
  });

  it('sets FAILED status on error event', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'fail', {
      events: [MockEvent.error('boom')],
    });

    expect(result.status).toBe('FAILED');
  });

  it('stores prompt in messages', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'my prompt', {
      events: [MockEvent.done('ok')],
    });

    expect(result.messages).toHaveLength(2);
    expect(result.messages[0]).toEqual({ role: 'user', content: 'my prompt' });
  });

  it('handles empty events list', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'test', { events: [] });

    expect(result.status).toBe('COMPLETED');
    expect(result.toolCalls).toHaveLength(0);
    expect(result.events).toHaveLength(0);
  });

  it('flushes pending tool call without result', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'test', {
      events: [
        MockEvent.toolCall('search', { q: 'test' }),
        MockEvent.done('done'),
      ],
      autoExecuteTools: false,
    });

    expect(result.toolCalls).toHaveLength(1);
    const tc = result.toolCalls[0] as { name: string; result?: unknown };
    expect(tc.name).toBe('search');
    expect(tc.result).toBeUndefined();
  });

  it('auto-executes tool functions when available', () => {
    const searchFn = (args: Record<string, unknown>) => `found: ${args.q}`;
    const agent = new Agent({
      name: 'test-agent',
      tools: [{ name: 'search', func: searchFn, description: 'search', inputSchema: {}, toolType: 'worker' }],
    });
    const result = mockRun(agent, 'test', {
      events: [
        MockEvent.toolCall('search', { q: 'hello' }),
        MockEvent.done('ok'),
      ],
    });

    expect(result.toolCalls).toHaveLength(1);
    const tc = result.toolCalls[0] as { name: string; result: unknown };
    expect(tc.result).toBe('found: hello');
    // Auto-execute should add a tool_result event
    expect(result.events.filter((e) => e.type === 'tool_result')).toHaveLength(1);
  });

  it('skips auto-execute when autoExecuteTools is false', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'test', {
      events: [
        MockEvent.toolCall('search', { q: 'hello' }),
        MockEvent.toolResult('search', 'manual result'),
        MockEvent.done('ok'),
      ],
      autoExecuteTools: false,
    });

    expect(result.toolCalls).toHaveLength(1);
    const tc = result.toolCalls[0] as { name: string; result: unknown };
    expect(tc.result).toBe('manual result');
  });

  it('handles multiple tool calls', () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = mockRun(agent, 'test', {
      events: [
        MockEvent.toolCall('search', { q: 'a' }),
        MockEvent.toolResult('search', 'r1'),
        MockEvent.toolCall('fetch', { url: 'b' }),
        MockEvent.toolResult('fetch', 'r2'),
        MockEvent.done('done'),
      ],
      autoExecuteTools: false,
    });

    expect(result.toolCalls).toHaveLength(2);
  });
});
