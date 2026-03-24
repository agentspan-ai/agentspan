/**
 * Retry on Error -- automatic retry logic with exponential back-off.
 *
 * Demonstrates:
 *   - Node retry policies via RetryPolicy
 *   - Handling transient failures gracefully
 *   - Tracking retry attempts in state
 *   - Practical use case: calling an unreliable external API with retries
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addNode("api_call", unreliableApiCall, { retry: new RetryPolicy(...) });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface RetryState {
  query: string;
  attempts: number;
  result: string;
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
let _callCount = 0;

function unreliableApiCall(state: RetryState): Partial<RetryState> {
  _callCount += 1;
  const attempt = (state.attempts ?? 0) + 1;

  // Simulate transient failures on early calls
  if (_callCount <= 2 && Math.random() < 0.7) {
    throw new Error(`Simulated transient network error on attempt ${attempt}`);
  }

  // Succeed -- mock LLM response
  const result = 'The speed of light in a vacuum is approximately 299,792,458 meters per second.';
  return { attempts: attempt, result };
}

function formatOutput(state: RetryState): Partial<RetryState> {
  return {
    result: `[Succeeded after ${state.attempts ?? 1} attempt(s)]\n${state.result}`,
  };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'retry_agent',

  invoke: async (input: Record<string, unknown>) => {
    const query = (input.input as string) ?? '';
    let state: RetryState = { query, attempts: 0, result: '' };

    // Retry loop (max 5 attempts)
    let lastError: Error | null = null;
    for (let i = 0; i < 5; i++) {
      try {
        state = { ...state, ...unreliableApiCall(state) };
        lastError = null;
        break;
      } catch (err) {
        lastError = err as Error;
        state = { ...state, attempts: state.attempts + 1 };
        // Exponential back-off (simulated)
      }
    }
    if (lastError) {
      state.result = `Failed after ${state.attempts} attempts: ${lastError.message}`;
    }

    state = { ...state, ...formatOutput(state) };
    return { output: state.result };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['api_call', {}],
      ['format', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'api_call'],
      ['api_call', 'format'],
      ['format', '__end__'],
    ],
  }),

  nodes: new Map([
    ['api_call', {}],
    ['format', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const query = (input.input as string) ?? '';
    let state: RetryState = { query, attempts: 0, result: '' };

    let lastError: Error | null = null;
    for (let i = 0; i < 5; i++) {
      try {
        state = { ...state, ...unreliableApiCall(state) };
        lastError = null;
        break;
      } catch (err) {
        lastError = err as Error;
        state = { ...state, attempts: state.attempts + 1 };
      }
    }
    if (lastError) {
      state.result = `Failed after ${state.attempts} attempts: ${lastError.message}`;
    }
    yield ['updates', { api_call: { attempts: state.attempts, result: state.result } }];

    state = { ...state, ...formatOutput(state) };
    yield ['updates', { format: { result: state.result } }];

    yield ['values', { output: state.result }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      graph,
      'What is the speed of light in meters per second?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
