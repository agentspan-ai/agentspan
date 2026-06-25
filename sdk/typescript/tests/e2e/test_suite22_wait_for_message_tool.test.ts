/**
 * Suite 22: WaitForMessage tool — deterministic compilation check.
 *
 * No LLM judging. Compiles agents via runtime.plan() and asserts the
 * waitForMessageTool lands in the compiled agentDef.tools with the correct
 * name, toolType, and config (matching the Java/Python reference wire format).
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime, waitForMessageTool, tool } from '@agentspan-ai/sdk';
import { z } from 'zod';
import { checkServerHealth, MODEL } from './helpers';

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available');
  runtime = new AgentRuntime();
});

afterAll(async () => {
  await runtime.shutdown();
});

// Pull the compiled agentDef.tools array out of a plan() result.
async function compiledTools(agent: Agent): Promise<Record<string, unknown>[]> {
  const plan = (await runtime.plan(agent)) as Record<string, unknown>;
  const wf = plan.workflowDef as Record<string, unknown>;
  const meta = wf.metadata as Record<string, unknown>;
  const ad = meta.agentDef as Record<string, unknown>;
  return (ad.tools ?? []) as Record<string, unknown>[];
}

describe('Suite 22: WaitForMessage tool', { timeout: 120_000 }, () => {
  it('compiles waitForMessageTool into agentDef.tools with correct wire shape', async () => {
    const agent = new Agent({
      name: 'e2e_ts_wait_for_message',
      model: MODEL,
      instructions: 'Call wait_for_message when you need to wait for input.',
      tools: [
        waitForMessageTool({
          name: 'wait_for_message',
          description: 'Wait until a message is sent to this agent.',
        }),
      ],
    });

    const tools = await compiledTools(agent);
    const wait = tools.find((t) => t.name === 'wait_for_message');
    expect(wait, 'wait_for_message tool missing from compiled agentDef').toBeDefined();
    expect(wait!.toolType).toBe('pull_workflow_messages');
    expect(wait!.config).toEqual({ batchSize: 1 });
    expect(wait!.config).not.toHaveProperty('blocking');
    expect(wait!.inputSchema).toEqual({ type: 'object', properties: {} });
  });

  it('non-blocking + custom batchSize compiles blocking=false', async () => {
    const agent = new Agent({
      name: 'e2e_ts_poll_messages',
      model: MODEL,
      instructions: 'Poll for messages.',
      tools: [
        waitForMessageTool({
          name: 'poll_messages',
          description: 'Poll for messages.',
          batchSize: 5,
          blocking: false,
        }),
      ],
    });

    const tools = await compiledTools(agent);
    const poll = tools.find((t) => t.name === 'poll_messages');
    expect(poll, 'poll_messages tool missing from compiled agentDef').toBeDefined();
    expect(poll!.toolType).toBe('pull_workflow_messages');
    expect(poll!.config).toEqual({ batchSize: 5, blocking: false });
  });

  it('counterfactual — an agent without the tool has no pull_workflow_messages tool', async () => {
    const noop = tool(async () => 'ok', {
      name: 'noop',
      description: 'A no-op worker tool.',
      inputSchema: z.object({}),
    });
    const agent = new Agent({
      name: 'e2e_ts_no_wait_tool',
      model: MODEL,
      instructions: 'A plain agent with one worker tool.',
      tools: [noop],
    });

    const tools = await compiledTools(agent);
    const waitTools = tools.filter((t) => t.toolType === 'pull_workflow_messages');
    expect(waitTools.length).toBe(0);
    // Sanity: the worker tool is present so we know compilation produced tools.
    expect(tools.some((t) => t.name === 'noop')).toBe(true);
  });
});
