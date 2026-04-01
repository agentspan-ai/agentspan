/**
 * Error Recovery -- StateGraph with try/catch in nodes for graceful degradation.
 *
 * Demonstrates:
 *   - Catching exceptions within StateGraph nodes
 *   - Storing error information in state for downstream handling
 *   - A fallback node that generates a graceful response on failure
 *   - Conditional routing based on whether an error occurred
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const RecoveryState = Annotation.Root({
  query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  data: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  error: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  response: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof RecoveryState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function fetchData(state: State): Partial<State> {
  const query = state.query;
  try {
    // Simulate a failure for queries containing 'fail' or 'error'
    if (query.toLowerCase().includes('fail') || query.toLowerCase().includes('error')) {
      throw new Error(`Simulated fetch failure for query: '${query}'`);
    }

    // Simulate successful data fetch
    const data =
      `Fetched data for '${query}': ` +
      'Sample dataset with 100 records, avg value 42.5, max 99, min 1.';
    return { data, error: '' };
  } catch (exc: any) {
    // Capture the error in state instead of crashing the graph
    return { data: '', error: String(exc.message ?? exc) };
  }
}

function shouldRecover(state: State): string {
  return state.error ? 'recover' : 'process';
}

async function processData(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a data analyst. Summarize the following data in one sentence.',
    ),
    new HumanMessage(state.data),
  ]);
  return { response: response.content as string };
}

async function recoverFromError(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'A data fetch error occurred. Apologize briefly, explain what may have gone wrong, ' +
        'and suggest 2 alternative approaches the user could try. Be concise.',
    ),
    new HumanMessage(`Error: ${state.error}\nOriginal query: ${state.query}`),
  ]);
  return { response: `[RECOVERED FROM ERROR]\n${response.content}` };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(RecoveryState);
builder.addNode('fetch', fetchData);
builder.addNode('process', processData);
builder.addNode('recover', recoverFromError);

builder.addEdge(START, 'fetch');
builder.addConditionalEdges('fetch', shouldRecover, {
  process: 'process',
  recover: 'recover',
});
builder.addEdge('process', END);
builder.addEdge('recover', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    console.log('=== Happy path ===');
    let result = await runtime.run(graph, 'sales data for Q4');
    console.log('Status:', result.status);
    result.printResult();

    console.log('\n=== Error recovery path ===');
    result = await runtime.run(graph, 'intentionally fail this query');
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('17-error-recovery.ts') || process.argv[1]?.endsWith('17-error-recovery.js')) {
  main().catch(console.error);
}
