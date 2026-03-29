/**
 * Retry on Error -- automatic retry logic with exponential back-off.
 *
 * Demonstrates:
 *   - Simulating transient failures and retrying until success
 *   - Tracking retry attempts in state
 *   - Using a try/catch wrapper in a node to implement retry logic
 *   - Practical use case: calling an unreliable external API with retries
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

let _callCount = 0;

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const RetryState = Annotation.Root({
  query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  attempts: Annotation<number>({
    reducer: (_prev: number, next: number) => next ?? _prev,
    default: () => 0,
  }),
  result: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  error: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof RetryState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
const MAX_RETRIES = 5;
const INITIAL_INTERVAL_MS = 100;
const BACKOFF_FACTOR = 2;

async function unreliableApiCall(state: State): Promise<Partial<State>> {
  _callCount += 1;
  const attempt = (state.attempts || 0) + 1;

  // Simulate transient failure on first two calls (70% chance)
  if (_callCount <= 2 && Math.random() < 0.7) {
    return {
      attempts: attempt,
      error: `Simulated transient network error on attempt ${attempt}`,
    };
  }

  const response = await llm.invoke([
    new SystemMessage('Answer the question concisely.'),
    new HumanMessage(state.query),
  ]);
  return { attempts: attempt, result: String(response.content).trim(), error: '' };
}

async function retryWrapper(state: State): Promise<Partial<State>> {
  let currentState = { ...state };
  for (let i = 0; i < MAX_RETRIES; i++) {
    const partial = await unreliableApiCall(currentState);
    currentState = { ...currentState, ...partial } as State;
    if (!currentState.error) {
      return {
        attempts: currentState.attempts,
        result: currentState.result,
        error: '',
      };
    }
    // Exponential backoff
    const delay = INITIAL_INTERVAL_MS * Math.pow(BACKOFF_FACTOR, i);
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
  return {
    attempts: currentState.attempts,
    result: `Failed after ${currentState.attempts} attempts: ${currentState.error}`,
    error: currentState.error,
  };
}

function formatOutput(state: State): Partial<State> {
  return {
    result: `[Succeeded after ${state.attempts || 1} attempt(s)]\n${state.result}`,
  };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(RetryState);
builder.addNode('api_call', retryWrapper);
builder.addNode('format', formatOutput);
builder.addEdge(START, 'api_call');
builder.addEdge('api_call', 'format');
builder.addEdge('format', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'What is the speed of light in meters per second?';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(graph);
    await runtime.serve(graph);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(graph, PROMPT);
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('23-retry-on-error.ts') || process.argv[1]?.endsWith('23-retry-on-error.js')) {
  main().catch(console.error);
}
