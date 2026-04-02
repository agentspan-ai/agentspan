/**
 * Parallel Branches -- StateGraph with two concurrent paths that merge.
 *
 * Demonstrates:
 *   - Fan-out from START to two parallel branches
 *   - Using Annotation list reducers to safely merge outputs
 *   - Fan-in merge node that combines results from both branches
 *   - Practical use case: parallel pros/cons analysis
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const ParallelState = Annotation.Root({
  topic: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  pros: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  cons: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  // Annotated with concat reducer so both branches can append safely
  branch_outputs: Annotation<string[]>({
    reducer: (prev: string[], next: string[]) => [...(prev ?? []), ...(next ?? [])],
    default: () => [],
  }),
  final_summary: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof ParallelState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function analyzePros(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('List 3 clear advantages or pros. Be concise and specific.'),
    new HumanMessage(`Topic: ${state.topic}`),
  ]);
  const content = response.content as string;
  return {
    pros: content,
    branch_outputs: [`PROS:\n${content}`],
  };
}

async function analyzeCons(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('List 3 clear disadvantages or cons. Be concise and specific.'),
    new HumanMessage(`Topic: ${state.topic}`),
  ]);
  const content = response.content as string;
  return {
    cons: content,
    branch_outputs: [`CONS:\n${content}`],
  };
}

async function mergeAndSummarize(state: State): Promise<Partial<State>> {
  const combined = state.branch_outputs.join('\n\n');
  const response = await llm.invoke([
    new SystemMessage(
      'You have received a pros and cons analysis. ' +
        'Write a balanced, one-paragraph conclusion with a clear recommendation.',
    ),
    new HumanMessage(`Topic: ${state.topic}\n\n${combined}`),
  ]);
  return { final_summary: response.content as string };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(ParallelState);
builder.addNode('pros_node', analyzePros);
builder.addNode('cons_node', analyzeCons);
builder.addNode('merge', mergeAndSummarize);

// Fan-out: both branches run in parallel from START
builder.addEdge(START, 'pros_node');
builder.addEdge(START, 'cons_node');

// Fan-in: both branches feed into merge
builder.addEdge('pros_node', 'merge');
builder.addEdge('cons_node', 'merge');
builder.addEdge('merge', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'remote work for software engineers';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents parallel_branches
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('16-parallel-branches.ts') || process.argv[1]?.endsWith('16-parallel-branches.js')) {
  main().catch(console.error);
}
