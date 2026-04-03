import type { AgentResult, AgentEvent } from '../types.js';
import { Agent } from '../agent.js';
import { makeAgentResult } from '../result.js';
import { getToolDef } from '../tool.js';
import { ConfigurationError } from '../errors.js';

/**
 * Options for mockRun.
 */
export interface MockRunOptions {
  /** Override tool implementations by name. */
  mockTools?: Record<string, Function>;
  /** Mock credentials injected into tool context. */
  mockCredentials?: Record<string, string>;
  /** Optional session ID. */
  sessionId?: string;
}

/**
 * Execute tools for a single agent, collecting events and toolCalls.
 */
async function executeTools(
  agent: Agent,
  options: MockRunOptions | undefined,
  events: AgentEvent[],
  toolCalls: Array<{ name: string; args: unknown; result: unknown }>,
): Promise<void> {
  const tools = agent.tools ?? [];
  for (const t of tools) {
    let def;
    try {
      def = getToolDef(t);
    } catch {
      continue;
    }
    if (!def) continue;

    const mockFn = options?.mockTools?.[def.name];
    const fn = mockFn ?? def.func;
    if (!fn) continue;

    const args = {};
    events.push({ type: 'tool_call', toolName: def.name, args });
    try {
      const result = await fn(args);
      events.push({ type: 'tool_result', toolName: def.name, result });
      toolCalls.push({ name: def.name, args, result });
    } catch (err) {
      events.push({ type: 'error', content: String(err) });
    }
  }
}

/**
 * Recursively simulate a sub-agent, collecting events into the parent arrays.
 */
async function simulateSubAgent(
  sub: Agent,
  options: MockRunOptions | undefined,
  events: AgentEvent[],
  toolCalls: Array<{ name: string; args: unknown; result: unknown }>,
): Promise<string> {
  // Execute this sub-agent's own tools
  await executeTools(sub, options, events, toolCalls);

  // Recurse into nested sub-agents
  if (sub.agents && sub.agents.length > 0) {
    await simulateSubAgents(sub, options, events, toolCalls);
  }

  const output = `Mock output from ${sub.name}`;
  events.push({
    type: 'done',
    output: { result: output },
  });
  return output;
}

/**
 * Simulate sub-agent orchestration based on strategy.
 */
async function simulateSubAgents(
  agent: Agent,
  options: MockRunOptions | undefined,
  events: AgentEvent[],
  toolCalls: Array<{ name: string; args: unknown; result: unknown }>,
): Promise<Record<string, unknown>> {
  const subResults: Record<string, unknown> = {};
  const strategy = agent.strategy ?? 'handoff';
  const subs = agent.agents ?? [];

  if (subs.length === 0) return subResults;

  switch (strategy) {
    case 'handoff':
    case 'router': {
      // Simulate handoff to the first sub-agent
      const target = subs[0];
      events.push({ type: 'handoff', target: target.name });
      const output = await simulateSubAgent(target, options, events, toolCalls);
      subResults[target.name] = output;
      break;
    }

    case 'sequential': {
      // Run all sub-agents in order
      for (const sub of subs) {
        events.push({ type: 'handoff', target: sub.name });
        const output = await simulateSubAgent(sub, options, events, toolCalls);
        subResults[sub.name] = output;
      }
      break;
    }

    case 'parallel': {
      // Run all sub-agents (simulated concurrently)
      const promises = subs.map(async (sub) => {
        events.push({ type: 'handoff', target: sub.name });
        const output = await simulateSubAgent(sub, options, events, toolCalls);
        subResults[sub.name] = output;
      });
      await Promise.all(promises);
      break;
    }

    default: {
      // For unknown strategies, hand off to first
      if (subs.length > 0) {
        const target = subs[0];
        events.push({ type: 'handoff', target: target.name });
        const output = await simulateSubAgent(target, options, events, toolCalls);
        subResults[target.name] = output;
      }
    }
  }

  return subResults;
}

/**
 * Execute an agent locally without a server connection.
 *
 * Walks agent.tools, attempts to extract a ToolDef for each,
 * executes each tool once with empty args (or via mockTools override),
 * collects events/toolCalls, and returns a completed AgentResult.
 *
 * For multi-agent setups, recursively simulates sub-agents based on the
 * declared strategy, producing handoff and done events for each.
 *
 * This is a TESTING utility — it does not run a real LLM loop.
 */
export async function mockRun(
  agent: Agent,
  prompt: string,
  options?: MockRunOptions,
): Promise<AgentResult> {
  const events: AgentEvent[] = [];
  const toolCalls: Array<{ name: string; args: unknown; result: unknown }> = [];
  let subResults: Record<string, unknown> = {};

  // Execute this agent's own tools
  await executeTools(agent, options, events, toolCalls);

  // Simulate sub-agent orchestration
  if (agent.agents && agent.agents.length > 0) {
    subResults = await simulateSubAgents(agent, options, events, toolCalls);
  }

  events.push({
    type: 'done',
    output: { result: `Mock execution of ${agent.name}` },
  });

  return makeAgentResult({
    executionId: 'mock-' + Date.now(),
    output: {
      result: `Mock execution of ${agent.name} with prompt: ${prompt}`,
    },
    status: 'COMPLETED',
    finishReason: 'stop',
    events,
    toolCalls,
    messages: [{ role: 'user', content: prompt }],
    subResults,
  });
}
