/**
 * Simple StateGraph -- custom query -> process -> generate pipeline.
 *
 * Demonstrates:
 *   - Defining a typed state schema with Annotation
 *   - Building a StateGraph with multiple sequential nodes
 *   - Connecting nodes with addEdge
 *   - Compiling the graph
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const QueryState = Annotation.Root({
  query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  refined_query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  output: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof QueryState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function validate(state: State): Partial<State> {
  let query = (state.query || '').trim();
  if (query === '') {
    query = 'What can you help me with?';
  }
  return { query };
}

function refine(state: State): Partial<State> {
  const refined = `Please provide a detailed and comprehensive explanation of: ${state.query}`;
  return { refined_query: refined };
}

function generate(state: State): Partial<State> {
  const q = state.refined_query || state.query;
  // In production this would call an LLM
  const answer =
    `Based on the query "${q.slice(0, 60)}...", Python is a versatile, ` +
    'high-level programming language created by Guido van Rossum in 1991. ' +
    'It emphasizes readability and supports multiple paradigms including ' +
    'procedural, object-oriented, and functional programming.';
  return { output: answer };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(QueryState);
builder.addNode('validate', validate);
builder.addNode('refine', refine);
builder.addNode('generate', generate);
builder.addEdge(START, 'validate');
builder.addEdge('validate', 'refine');
builder.addEdge('refine', 'generate');
builder.addEdge('generate', END);

const graph = builder.compile();

// Add agentspan metadata for extraction (no LLM in this pipeline example)
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
    const result = await runtime.run(graph, 'Tell me about Python');
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents simple_stategraph
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('04-simple-stategraph.ts') || process.argv[1]?.endsWith('04-simple-stategraph.js')) {
  main().catch(console.error);
}
