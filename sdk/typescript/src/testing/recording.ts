import type { AgentResult, AgentEvent } from '../types.js';
import { Agent } from '../agent.js';
import { makeAgentResult } from '../result.js';
import { mockRun, type MockRunOptions } from './mock.js';
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * Fixture format stored on disk.
 */
export interface RecordingFixture {
  agent: { name: string; model?: string };
  prompt: string;
  events: AgentEvent[];
  result: {
    output: Record<string, unknown>;
    executionId: string;
    status: string;
    finishReason: string;
    error?: string;
    toolCalls: unknown[];
    messages: unknown[];
  };
  timestamp: number;
}

/**
 * Options for recording an agent execution.
 */
export interface RecordOptions extends MockRunOptions {
  /** Path to write the JSON fixture file. */
  fixturePath: string;
}

/**
 * Run an agent via mockRun, capture all events to a JSON fixture file, and return the result.
 */
export async function record(
  agent: Agent,
  prompt: string,
  options: RecordOptions,
): Promise<AgentResult> {
  const { fixturePath, ...mockOptions } = options;
  const result = await mockRun(agent, prompt, mockOptions);

  const fixture: RecordingFixture = {
    agent: { name: agent.name, model: agent.model },
    prompt,
    events: result.events,
    result: {
      output: result.output,
      executionId: result.executionId,
      status: result.status,
      finishReason: result.finishReason,
      error: result.error,
      toolCalls: result.toolCalls,
      messages: result.messages,
    },
    timestamp: Date.now(),
  };

  // Ensure directory exists
  const dir = path.dirname(fixturePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(fixturePath, JSON.stringify(fixture, null, 2), 'utf-8');

  return result;
}

/**
 * Load a JSON fixture and reconstruct an AgentResult.
 */
export function replay(fixturePath: string): AgentResult {
  const content = fs.readFileSync(fixturePath, 'utf-8');
  const fixture = JSON.parse(content) as RecordingFixture;

  return makeAgentResult({
    output: fixture.result.output,
    executionId: fixture.result.executionId,
    status: fixture.result.status,
    finishReason: fixture.result.finishReason,
    error: fixture.result.error,
    events: fixture.events,
    toolCalls: fixture.result.toolCalls,
    messages: fixture.result.messages,
  });
}
