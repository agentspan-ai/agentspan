import type { AgentResult, Status } from '../types.js';

/**
 * Assert that a specific tool was called during execution.
 * Throws if no `tool_call` event with the given toolName is found.
 */
export function assertToolUsed(result: AgentResult, toolName: string): void {
  const found = result.events.some(
    (e) => e.type === 'tool_call' && e.toolName === toolName,
  );
  if (!found) {
    throw new Error(`Expected tool "${toolName}" to have been used`);
  }
}

/**
 * Assert that a guardrail passed during execution.
 * Throws if no `guardrail_pass` event with the given name is found.
 */
export function assertGuardrailPassed(
  result: AgentResult,
  name: string,
): void {
  const found = result.events.some(
    (e) => e.type === 'guardrail_pass' && e.guardrailName === name,
  );
  if (!found) {
    throw new Error(`Expected guardrail "${name}" to have passed`);
  }
}

/**
 * Assert that a sub-agent ran during execution.
 * Checks events for done events with matching output, or subResults for the agent name.
 */
export function assertAgentRan(
  result: AgentResult,
  agentName: string,
): void {
  // Check subResults
  if (result.subResults && agentName in result.subResults) {
    return;
  }

  // Check events for agent-related activity
  const found = result.events.some(
    (e) =>
      (e.type === 'done' &&
        e.output != null &&
        JSON.stringify(e.output).includes(agentName)) ||
      (e.type === 'handoff' && e.target === agentName),
  );
  if (!found) {
    throw new Error(`Expected agent "${agentName}" to have run`);
  }
}

/**
 * Assert that a handoff to a target agent occurred.
 * Throws if no `handoff` event with the given target is found.
 */
export function assertHandoffTo(
  result: AgentResult,
  target: string,
): void {
  const found = result.events.some(
    (e) => e.type === 'handoff' && e.target === target,
  );
  if (!found) {
    throw new Error(`Expected handoff to "${target}"`);
  }
}

/**
 * Assert that the result has a specific status.
 */
export function assertStatus(result: AgentResult, status: Status): void {
  if (result.status !== status) {
    throw new Error(`Expected status "${status}", got "${result.status}"`);
  }
}

/**
 * Assert that no error events occurred during execution.
 */
export function assertNoErrors(result: AgentResult): void {
  const errorEvents = result.events.filter((e) => e.type === 'error');
  if (errorEvents.length > 0) {
    const messages = errorEvents
      .map((e) => e.content ?? 'unknown error')
      .join('; ');
    throw new Error(`Expected no errors, but found ${errorEvents.length}: ${messages}`);
  }
}
