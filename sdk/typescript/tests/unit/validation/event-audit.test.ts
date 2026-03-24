import { describe, it, expect } from 'vitest';
import { auditToolEvents, type ToolAuditEntry } from '../../../validation/checks/event-audit.js';
import type { AgentEvent } from '../../../src/types.js';

describe('auditToolEvents', () => {
  it('returns empty array for no events', () => {
    const result = auditToolEvents([]);
    expect(result).toEqual([]);
  });

  it('returns empty array when no tool_call events exist', () => {
    const events: AgentEvent[] = [
      { type: 'thinking', content: 'pondering...' },
      { type: 'message', content: 'hello' },
      { type: 'done' },
    ];
    const result = auditToolEvents(events);
    expect(result).toEqual([]);
  });

  it('marks tool as succeeded when tool_result follows tool_call', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'get_weather', args: { city: 'NYC' } },
      { type: 'tool_result', toolName: 'get_weather', result: { temp: 72 } },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      toolName: 'get_weather',
      called: true,
      succeeded: true,
      retriedAndFixed: false,
      failedPermanently: false,
    });
  });

  it('marks tool as failedPermanently when no tool_result exists', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'search', args: { query: 'test' } },
      { type: 'thinking', content: 'hmm...' },
      { type: 'done' },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(1);
    expect(result[0].failedPermanently).toBe(true);
    expect(result[0].succeeded).toBe(false);
  });

  it('marks tool as failedPermanently when tool_result is an error with no retry', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'api_call', args: {} },
      { type: 'tool_result', toolName: 'api_call', result: { error: 'timeout' } },
      { type: 'done' },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(1);
    expect(result[0].failedPermanently).toBe(true);
    expect(result[0].succeeded).toBe(false);
    expect(result[0].retriedAndFixed).toBe(false);
  });

  it('marks retriedAndFixed when tool errors then retries successfully', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'api_call', args: {} },
      { type: 'tool_result', toolName: 'api_call', result: { error: 'rate limit' } },
      { type: 'thinking', content: 'retrying...' },
      { type: 'tool_call', toolName: 'api_call', args: {} },
      { type: 'tool_result', toolName: 'api_call', result: { data: 'success' } },
    ];
    const result = auditToolEvents(events);
    // First call is the one that gets the retriedAndFixed flag
    expect(result).toHaveLength(1);
    expect(result[0].retriedAndFixed).toBe(true);
    expect(result[0].failedPermanently).toBe(false);
  });

  it('handles multiple different tools independently', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'get_weather', args: { city: 'NYC' } },
      { type: 'tool_result', toolName: 'get_weather', result: { temp: 72 } },
      { type: 'tool_call', toolName: 'search', args: { query: 'test' } },
      { type: 'tool_result', toolName: 'search', result: { results: [] } },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(2);
    expect(result[0].toolName).toBe('get_weather');
    expect(result[0].succeeded).toBe(true);
    expect(result[1].toolName).toBe('search');
    expect(result[1].succeeded).toBe(true);
  });

  it('handles tool_result with error in content string', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'calculate', args: { expr: '1/0' } },
      { type: 'tool_result', toolName: 'calculate', content: 'Error: division by zero' },
      { type: 'done' },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(1);
    expect(result[0].failedPermanently).toBe(true);
  });

  it('handles tool_result with isError flag', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'fetch', args: {} },
      { type: 'tool_result', toolName: 'fetch', result: { isError: true, message: 'not found' } },
      { type: 'done' },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(1);
    expect(result[0].failedPermanently).toBe(true);
  });

  it('handles unknown toolName gracefully', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call' } as AgentEvent,
      { type: 'tool_result' } as AgentEvent,
    ];
    const result = auditToolEvents(events);
    // Both have undefined toolName, so they match on 'unknown'
    expect(result).toHaveLength(1);
    expect(result[0].toolName).toBe('unknown');
  });

  it('correctly handles interleaved tool calls for different tools', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'a', args: {} },
      { type: 'tool_call', toolName: 'b', args: {} },
      { type: 'tool_result', toolName: 'b', result: { ok: true } },
      { type: 'tool_result', toolName: 'a', result: { ok: true } },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(2);
    expect(result[0].toolName).toBe('a');
    expect(result[0].succeeded).toBe(true);
    expect(result[1].toolName).toBe('b');
    expect(result[1].succeeded).toBe(true);
  });

  it('handles retry that also fails', () => {
    const events: AgentEvent[] = [
      { type: 'tool_call', toolName: 'flaky', args: {} },
      { type: 'tool_result', toolName: 'flaky', result: { error: 'fail 1' } },
      { type: 'tool_call', toolName: 'flaky', args: {} },
      { type: 'tool_result', toolName: 'flaky', result: { error: 'fail 2' } },
    ];
    const result = auditToolEvents(events);
    expect(result).toHaveLength(1);
    expect(result[0].failedPermanently).toBe(true);
    expect(result[0].retriedAndFixed).toBe(false);
  });
});
