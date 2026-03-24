/**
 * Tool call -> tool result event audit.
 *
 * Walks through agent events and pairs each tool_call with its matching
 * tool_result. Handles retries: if a tool_result is an error but a subsequent
 * call to the same tool succeeds, marks retriedAndFixed.
 */

import type { AgentEvent } from '../../src/types.js';

export interface ToolAuditEntry {
  toolName: string;
  called: boolean;
  succeeded: boolean;
  retriedAndFixed: boolean;
  failedPermanently: boolean;
}

/**
 * Determine whether a tool_result event represents an error.
 */
function isToolResultError(event: AgentEvent): boolean {
  if (event.type !== 'tool_result') return false;

  // Check for explicit error content
  const result = event.result;
  if (result && typeof result === 'object') {
    const r = result as Record<string, unknown>;
    if (r.error || r.isError) return true;
  }
  if (typeof event.content === 'string') {
    const lower = event.content.toLowerCase();
    if (lower.includes('error') || lower.includes('exception') || lower.includes('traceback')) {
      return true;
    }
  }
  return false;
}

/**
 * Find the next tool_result event for the given tool name, starting from index.
 */
function findNextToolResult(
  events: AgentEvent[],
  toolName: string,
  startIndex: number,
): { event: AgentEvent; index: number } | null {
  for (let i = startIndex; i < events.length; i++) {
    const e = events[i];
    if (e.type === 'tool_result' && e.toolName === toolName) {
      return { event: e, index: i };
    }
  }
  return null;
}

/**
 * Find the next tool_call event for the given tool name, starting from index.
 */
function findNextToolCall(
  events: AgentEvent[],
  toolName: string,
  startIndex: number,
): { event: AgentEvent; index: number } | null {
  for (let i = startIndex; i < events.length; i++) {
    const e = events[i];
    if (e.type === 'tool_call' && e.toolName === toolName) {
      return { event: e, index: i };
    }
  }
  return null;
}

/**
 * Audit all tool_call events in the event stream.
 *
 * For each tool_call:
 * 1. Walk forward for a matching tool_result with the same toolName
 * 2. If tool_result exists and is NOT an error -> succeeded: true
 * 3. If tool_result is an error:
 *    a. Check if a subsequent tool_call for the same tool exists
 *    b. If yes, and its tool_result succeeds -> retriedAndFixed: true
 *    c. If no retry or retry also failed -> failedPermanently: true
 * 4. If no tool_result at all -> failedPermanently: true
 */
export function auditToolEvents(events: AgentEvent[]): ToolAuditEntry[] {
  const entries: ToolAuditEntry[] = [];
  const processed = new Set<number>(); // track processed tool_call indices

  for (let i = 0; i < events.length; i++) {
    const event = events[i];
    if (event.type !== 'tool_call') continue;
    if (processed.has(i)) continue;

    const toolName = event.toolName ?? 'unknown';
    processed.add(i);

    const entry: ToolAuditEntry = {
      toolName,
      called: true,
      succeeded: false,
      retriedAndFixed: false,
      failedPermanently: false,
    };

    // Find matching tool_result
    const resultMatch = findNextToolResult(events, toolName, i + 1);

    if (!resultMatch) {
      // No tool_result found
      entry.failedPermanently = true;
      entries.push(entry);
      continue;
    }

    if (!isToolResultError(resultMatch.event)) {
      // Successful result
      entry.succeeded = true;
      entries.push(entry);
      continue;
    }

    // Error result — check for retry
    const retryCall = findNextToolCall(events, toolName, resultMatch.index + 1);
    if (retryCall) {
      processed.add(retryCall.index);
      const retryResult = findNextToolResult(events, toolName, retryCall.index + 1);

      if (retryResult && !isToolResultError(retryResult.event)) {
        entry.retriedAndFixed = true;
        entries.push(entry);
        continue;
      }
    }

    // No retry or retry also failed
    entry.failedPermanently = true;
    entries.push(entry);
  }

  return entries;
}
