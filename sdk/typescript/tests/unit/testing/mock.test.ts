import { describe, it, expect, vi } from 'vitest';
import { mockRun } from '../../../src/testing/mock.js';
import { Agent } from '../../../src/agent.js';
import { tool } from '../../../src/tool.js';
import { z } from 'zod';

// ── Helper: create a simple tool ────────────────────────

function makeGreetTool() {
  return tool(
    async (args: { name?: string }) => `Hello, ${args.name ?? 'world'}!`,
    {
      name: 'greet',
      description: 'Greet someone',
      inputSchema: z.object({ name: z.string().optional() }),
    },
  );
}

function makeFailTool() {
  return tool(
    async () => {
      throw new Error('Tool failed');
    },
    {
      name: 'fail_tool',
      description: 'A tool that always fails',
      inputSchema: z.object({}),
    },
  );
}

// ── Tests ────────────────────────────────────────────────

describe('mockRun', () => {
  it('executes agent tools and returns AgentResult', async () => {
    const greet = makeGreetTool();
    const agent = new Agent({
      name: 'test-agent',
      model: 'gpt-4',
      tools: [greet],
    });

    const result = await mockRun(agent, 'Say hello');

    expect(result.status).toBe('COMPLETED');
    expect(result.finishReason).toBe('stop');
    expect(result.isSuccess).toBe(true);
    expect(result.output).toBeDefined();
    expect(JSON.stringify(result.output)).toContain('test-agent');
    expect(result.messages).toHaveLength(1);
    expect(result.messages[0]).toEqual({ role: 'user', content: 'Say hello' });
  });

  it('generates tool_call and tool_result events', async () => {
    const greet = makeGreetTool();
    const agent = new Agent({
      name: 'test-agent',
      tools: [greet],
    });

    const result = await mockRun(agent, 'hi');

    const toolCallEvents = result.events.filter(
      (e) => e.type === 'tool_call',
    );
    const toolResultEvents = result.events.filter(
      (e) => e.type === 'tool_result',
    );

    expect(toolCallEvents).toHaveLength(1);
    expect(toolCallEvents[0].toolName).toBe('greet');

    expect(toolResultEvents).toHaveLength(1);
    expect(toolResultEvents[0].toolName).toBe('greet');
    expect(toolResultEvents[0].result).toBe('Hello, world!');
  });

  it('populates toolCalls array', async () => {
    const greet = makeGreetTool();
    const agent = new Agent({
      name: 'test-agent',
      tools: [greet],
    });

    const result = await mockRun(agent, 'hi');

    expect(result.toolCalls).toHaveLength(1);
    const tc = result.toolCalls[0] as {
      name: string;
      args: unknown;
      result: unknown;
    };
    expect(tc.name).toBe('greet');
    expect(tc.result).toBe('Hello, world!');
  });

  it('emits a done event', async () => {
    const agent = new Agent({ name: 'empty-agent' });
    const result = await mockRun(agent, 'test');

    const doneEvents = result.events.filter((e) => e.type === 'done');
    expect(doneEvents).toHaveLength(1);
  });

  it('uses mockTools to override tool implementations', async () => {
    const greet = makeGreetTool();
    const agent = new Agent({
      name: 'test-agent',
      tools: [greet],
    });

    const mockFn = vi.fn().mockResolvedValue('Mocked greeting!');

    const result = await mockRun(agent, 'hi', {
      mockTools: { greet: mockFn },
    });

    expect(mockFn).toHaveBeenCalledOnce();
    const tc = result.toolCalls[0] as {
      name: string;
      result: unknown;
    };
    expect(tc.result).toBe('Mocked greeting!');
  });

  it('handles tool errors with error events', async () => {
    const fail = makeFailTool();
    const agent = new Agent({
      name: 'test-agent',
      tools: [fail],
    });

    const result = await mockRun(agent, 'try');

    const errorEvents = result.events.filter((e) => e.type === 'error');
    expect(errorEvents).toHaveLength(1);
    expect(errorEvents[0].content).toContain('Tool failed');
    // The result should still be COMPLETED because mockRun always returns COMPLETED
    expect(result.status).toBe('COMPLETED');
  });

  it('handles agent with no tools', async () => {
    const agent = new Agent({ name: 'no-tools' });
    const result = await mockRun(agent, 'test');

    expect(result.status).toBe('COMPLETED');
    expect(result.toolCalls).toHaveLength(0);
    // Only the done event
    expect(result.events).toHaveLength(1);
    expect(result.events[0].type).toBe('done');
  });

  it('includes prompt in output', async () => {
    const agent = new Agent({ name: 'test-agent' });
    const result = await mockRun(agent, 'my specific prompt');

    expect(JSON.stringify(result.output)).toContain('my specific prompt');
  });

  it('handles multiple tools', async () => {
    const greet = makeGreetTool();
    const fail = makeFailTool();
    const agent = new Agent({
      name: 'multi',
      tools: [greet, fail],
    });

    const result = await mockRun(agent, 'test');

    // greet succeeds, fail errors
    const toolCallEvents = result.events.filter(
      (e) => e.type === 'tool_call',
    );
    expect(toolCallEvents).toHaveLength(2);

    const errorEvents = result.events.filter((e) => e.type === 'error');
    expect(errorEvents).toHaveLength(1);

    // Only greet should be in toolCalls (fail_tool threw)
    expect(result.toolCalls).toHaveLength(1);
  });

  it('accepts mockCredentials option', async () => {
    const agent = new Agent({ name: 'creds-agent' });
    const result = await mockRun(agent, 'test', {
      mockCredentials: { API_KEY: 'mock-key-123' },
    });

    expect(result.status).toBe('COMPLETED');
  });

  it('accepts sessionId option', async () => {
    const agent = new Agent({ name: 'session-agent' });
    const result = await mockRun(agent, 'test', {
      sessionId: 'sess-abc',
    });

    expect(result.status).toBe('COMPLETED');
  });

  it('generates a workflowId starting with mock-', async () => {
    const agent = new Agent({ name: 'test' });
    const result = await mockRun(agent, 'hi');

    expect(result.workflowId).toMatch(/^mock-\d+$/);
  });
});
