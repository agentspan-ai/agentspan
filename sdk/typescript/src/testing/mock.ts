// ── Mock execution — deterministic agent testing without LLM or server ──
//
// Provides MockEvent (a factory for AgentEvent objects) and mockRun which
// builds an AgentResult from a scripted event sequence.

import type { AgentEvent, AgentResult } from '../types.js';
import type { Agent } from '../agent.js';
import { makeAgentResult } from '../result.js';

// ── MockEvent factory ────────────────────────────────────────────────

/**
 * Factory for creating AgentEvent instances in tests.
 *
 * Each static method returns a properly-typed AgentEvent with the correct
 * `type` field set. Use these to script event sequences for `mockRun`.
 */
export class MockEvent {
  static thinking(content: string): AgentEvent {
    return { type: 'thinking', content };
  }

  static toolCall(name: string, args?: Record<string, unknown>): AgentEvent {
    return { type: 'tool_call', toolName: name, args: args ?? {} };
  }

  static toolResult(name: string, result: unknown): AgentEvent {
    return { type: 'tool_result', toolName: name, result };
  }

  static handoff(target: string): AgentEvent {
    return { type: 'handoff', target };
  }

  static message(content: string): AgentEvent {
    return { type: 'message', content };
  }

  static guardrailPass(name: string, content: string = ''): AgentEvent {
    return { type: 'guardrail_pass', guardrailName: name, content };
  }

  static guardrailFail(name: string, content: string = ''): AgentEvent {
    return { type: 'guardrail_fail', guardrailName: name, content };
  }

  static waiting(content: string = ''): AgentEvent {
    return { type: 'waiting', content };
  }

  static done(output: unknown): AgentEvent {
    return { type: 'done', output };
  }

  static error(content: string): AgentEvent {
    return { type: 'error', content };
  }
}

// ── Tool resolution helper ───────────────────────────────────────────

function resolveToolFunc(
  agent: Agent,
  toolName: string,
): ((...args: unknown[]) => unknown) | null {
  if (!agent.tools || agent.tools.length === 0) return null;

  for (const t of agent.tools) {
    // Handle objects with name + func (ToolDef-like)
    const def = t as { name?: string; func?: Function };
    if (def.name === toolName && typeof def.func === 'function') {
      return def.func as (...args: unknown[]) => unknown;
    }
    // Handle plain functions with a name property
    if (typeof t === 'function' && (t as Function).name === toolName) {
      return t as (...args: unknown[]) => unknown;
    }
  }
  return null;
}

// ── mockRun ──────────────────────────────────────────────────────────

export interface MockRunOptions {
  events: AgentEvent[];
  autoExecuteTools?: boolean;
}

/**
 * Build an AgentResult from a scripted event sequence.
 *
 * This function does NOT call any LLM or server. It walks the provided
 * events, optionally executes real tool functions when a tool_call is
 * encountered, and assembles the result.
 *
 * @param agent - The Agent definition (used to resolve tool functions).
 * @param prompt - The user prompt (stored in messages for context).
 * @param options - Events to replay and execution options.
 */
export function mockRun(
  agent: Agent,
  prompt: string,
  options: MockRunOptions,
): AgentResult {
  const { events, autoExecuteTools = true } = options;

  const processed: AgentEvent[] = [];
  const toolCalls: Array<{ name: string; args: unknown; result?: unknown }> = [];
  let output: unknown = undefined;
  let status = 'COMPLETED';
  let pendingCall: { name: string; args: unknown; result?: unknown } | null =
    null;

  for (const ev of events) {
    processed.push(ev);

    if (ev.type === 'tool_call') {
      pendingCall = { name: ev.toolName ?? '', args: ev.args };

      if (autoExecuteTools) {
        const func = resolveToolFunc(agent, ev.toolName ?? '');
        if (func !== null) {
          let toolResult: unknown;
          try {
            toolResult = func(ev.args ?? {});
          } catch (err) {
            toolResult = `Error: ${err}`;
          }
          const resultEvent: AgentEvent = {
            type: 'tool_result',
            toolName: ev.toolName,
            result: toolResult,
          };
          processed.push(resultEvent);
          pendingCall.result = toolResult;
          toolCalls.push(pendingCall);
          pendingCall = null;
        }
      }
    } else if (ev.type === 'tool_result') {
      if (pendingCall !== null) {
        pendingCall.result = ev.result;
        toolCalls.push(pendingCall);
        pendingCall = null;
      } else {
        toolCalls.push({ name: ev.toolName ?? '', args: ev.args, result: ev.result });
      }
    } else if (ev.type === 'done') {
      output = ev.output;
    } else if (ev.type === 'error') {
      output = ev.content;
      status = 'FAILED';
    }
  }

  // Flush any pending tool call without result
  if (pendingCall !== null) {
    toolCalls.push(pendingCall);
  }

  const messages: Array<{ role: string; content: unknown }> = [
    { role: 'user', content: prompt },
  ];
  if (output !== undefined) {
    messages.push({ role: 'assistant', content: String(output) });
  }

  return makeAgentResult({
    executionId: 'mock',
    output,
    status,
    events: processed,
    toolCalls,
    messages,
  });
}
