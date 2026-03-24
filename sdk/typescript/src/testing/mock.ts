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
 * Execute an agent locally without a server connection.
 *
 * Walks agent.tools, attempts to extract a ToolDef for each,
 * executes each tool once with empty args (or via mockTools override),
 * collects events/toolCalls, and returns a completed AgentResult.
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

  // Simulate tool execution
  const tools = agent.tools ?? [];
  for (const t of tools) {
    let def;
    try {
      def = getToolDef(t);
    } catch {
      // Skip unrecognized tool formats
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

  events.push({
    type: 'done',
    output: { result: `Mock execution of ${agent.name}` },
  });

  return makeAgentResult({
    workflowId: 'mock-' + Date.now(),
    output: {
      result: `Mock execution of ${agent.name} with prompt: ${prompt}`,
    },
    status: 'COMPLETED',
    finishReason: 'stop',
    events,
    toolCalls,
    messages: [{ role: 'user', content: prompt }],
  });
}
