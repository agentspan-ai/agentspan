// ── Record and replay agent execution traces ─────────────────────────
//
// Usage:
//   record(result, "tests/recordings/weather.json");
//   const replayed = replay("tests/recordings/weather.json");

import type { AgentResult, AgentEvent, TokenUsage } from '../types.js';
import { makeAgentResult } from '../result.js';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ── Serialization helpers ────────────────────────────────────────────

function eventToDict(event: AgentEvent): Record<string, unknown> {
  const d: Record<string, unknown> = { type: event.type };
  if (event.content != null) d.content = event.content;
  if (event.toolName != null) d.toolName = event.toolName;
  if (event.args != null) d.args = event.args;
  if (event.result !== undefined) d.result = event.result;
  if (event.target != null) d.target = event.target;
  if (event.output !== undefined) d.output = event.output;
  if (event.executionId) d.executionId = event.executionId;
  if (event.guardrailName != null) d.guardrailName = event.guardrailName;
  if (event.timestamp != null) d.timestamp = event.timestamp;
  return d;
}

function dictToEvent(d: Record<string, unknown>): AgentEvent {
  return {
    type: (d.type as string) ?? '',
    content: d.content as string | undefined,
    toolName: d.toolName as string | undefined,
    args: d.args as Record<string, unknown> | undefined,
    result: d.result,
    target: d.target as string | undefined,
    output: d.output,
    executionId: d.executionId as string | undefined,
    guardrailName: d.guardrailName as string | undefined,
    timestamp: d.timestamp as number | undefined,
  };
}

function resultToDict(result: AgentResult): Record<string, unknown> {
  const d: Record<string, unknown> = {
    output: result.output,
    executionId: result.executionId,
    messages: result.messages,
    toolCalls: result.toolCalls,
    status: result.status,
    finishReason: result.finishReason,
    metadata: result.metadata,
    events: result.events.map(eventToDict),
  };
  if (result.correlationId) d.correlationId = result.correlationId;
  if (result.error) d.error = result.error;
  if (result.tokenUsage) {
    d.tokenUsage = {
      promptTokens: result.tokenUsage.promptTokens,
      completionTokens: result.tokenUsage.completionTokens,
      totalTokens: result.tokenUsage.totalTokens,
    };
  }
  if (result.subResults) d.subResults = result.subResults;
  return d;
}

function dictToResult(d: Record<string, unknown>): AgentResult {
  let tokenUsage: TokenUsage | undefined;
  if (d.tokenUsage) {
    const tu = d.tokenUsage as Record<string, number>;
    tokenUsage = {
      promptTokens: tu.promptTokens ?? 0,
      completionTokens: tu.completionTokens ?? 0,
      totalTokens: tu.totalTokens ?? 0,
    };
  }

  return makeAgentResult({
    output: d.output,
    executionId: d.executionId as string,
    correlationId: d.correlationId as string | undefined,
    messages: (d.messages as unknown[]) ?? [],
    toolCalls: (d.toolCalls as unknown[]) ?? [],
    status: d.status as string,
    finishReason: d.finishReason as string,
    error: d.error as string | undefined,
    tokenUsage,
    metadata: d.metadata as Record<string, unknown> | undefined,
    events: ((d.events as Record<string, unknown>[]) ?? []).map(dictToEvent),
    subResults: d.subResults as Record<string, unknown> | undefined,
  });
}

// ── Public API ───────────────────────────────────────────────────────

/**
 * Save an AgentResult to a JSON file.
 */
export function record(result: AgentResult, filePath: string): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  const data = resultToDict(result);
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

/**
 * Load a recorded AgentResult from a JSON file.
 */
export function replay(filePath: string): AgentResult {
  const content = fs.readFileSync(filePath, 'utf-8');
  const data = JSON.parse(content) as Record<string, unknown>;
  return dictToResult(data);
}
