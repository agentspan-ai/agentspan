/**
 * Simple StateGraph -- custom query → refine → answer pipeline.
 *
 * Demonstrates:
 *   - Defining a typed state schema with Annotation
 *   - Building a StateGraph with multiple sequential nodes
 *   - LLM calls inside node functions (detected by Agentspan for interception)
 *   - Connecting nodes with addEdge
 *   - Compiling and naming the graph
 *
 * Matches Python example: examples/langgraph/04_simple_stategraph.py
 * Same graph structure: validate → refine → answer (3 nodes, 2 with LLM calls)
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
 *   - OPENAI_API_KEY for ChatOpenAI
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '@agentspan-ai/sdk';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
// NOTE: TS LangGraph forbids node names that match state attribute names.
// Python uses "answer" for both the state field and the node name.
// Here we use "result" for the state field so the node can be named "answer".
const QueryState = Annotation.Root({
  query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  refined_query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  result: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof QueryState.State;

// ---------------------------------------------------------------------------
// Node functions (same logic as Python version)
// ---------------------------------------------------------------------------
function validate_query(state: State): Partial<State> {
  let query = (state.query || '').trim();
  if (query === '') {
    query = 'What can you help me with?';
  }
  return { query, refined_query: '', result: '' };
}

async function refine_query(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('Rewrite the user query to be more specific and clear. Return only the rewritten query.'),
    new HumanMessage(state.query),
  ]);
  return { refined_query: (response.content as string).trim() };
}

async function generate_answer(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('You are a knowledgeable assistant. Answer the question clearly and concisely.'),
    new HumanMessage(state.refined_query || state.query),
  ]);
  return { result: (response.content as string).trim() };
}

// ---------------------------------------------------------------------------
// Build the graph (same structure as Python: validate → refine → answer)
// ---------------------------------------------------------------------------
const builder = new StateGraph(QueryState);
builder.addNode('validate', validate_query);
builder.addNode('refine', refine_query);
builder.addNode('answer', generate_answer);
builder.addEdge(START, 'validate');
builder.addEdge('validate', 'refine');
builder.addEdge('refine', 'answer');
builder.addEdge('answer', END);

const graph = builder.compile({ name: "query_pipeline" });

// Add agentspan metadata for graph-structure extraction.
// Do NOT set tools on StateGraphs — only model + framework.
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
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

main().catch(console.error);
