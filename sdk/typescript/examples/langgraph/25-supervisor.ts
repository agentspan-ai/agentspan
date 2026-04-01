/**
 * Supervisor -- multi-agent supervisor pattern.
 *
 * Demonstrates:
 *   - A supervisor that decides which specialist agent to call next
 *   - Routing control flow based on the supervisor's decision
 *   - Collecting outputs from specialized sub-agents
 *   - Practical use case: research -> writing -> editing pipeline with supervisor control
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const SupervisorState = Annotation.Root({
  task: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  research: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  draft: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  final_article: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  next_agent: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  completed: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
});

type State = typeof SupervisorState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function supervisor(state: State): Partial<State> {
  const completed = state.completed || [];
  if (!completed.includes('researcher')) return { next_agent: 'researcher' };
  if (!completed.includes('writer')) return { next_agent: 'writer' };
  if (!completed.includes('editor')) return { next_agent: 'editor' };
  return { next_agent: 'FINISH' };
}

async function researcher(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a researcher. Gather key facts and insights about the topic in 3-5 bullet points.',
    ),
    new HumanMessage(`Topic: ${state.task}`),
  ]);
  const completed = [...(state.completed || []), 'researcher'];
  return { research: String(response.content).trim(), completed };
}

async function writer(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a writer. Using the research notes, write a short article (3 paragraphs).',
    ),
    new HumanMessage(`Topic: ${state.task}\n\nResearch:\n${state.research}`),
  ]);
  const completed = [...(state.completed || []), 'writer'];
  return { draft: String(response.content).trim(), completed };
}

async function editor(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are an editor. Improve clarity, flow, and correctness of the article. Return the polished version only.',
    ),
    new HumanMessage(state.draft),
  ]);
  const completed = [...(state.completed || []), 'editor'];
  return { final_article: String(response.content).trim(), completed };
}

function route(state: State): string {
  return state.next_agent || 'FINISH';
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(SupervisorState);
builder.addNode('supervisor', supervisor);
builder.addNode('researcher', researcher);
builder.addNode('writer', writer);
builder.addNode('editor', editor);

builder.addEdge(START, 'supervisor');
builder.addConditionalEdges('supervisor', route, {
  researcher: 'researcher',
  writer: 'writer',
  editor: 'editor',
  FINISH: END,
});
builder.addEdge('researcher', 'supervisor');
builder.addEdge('writer', 'supervisor');
builder.addEdge('editor', 'supervisor');

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'The impact of large language models on software development';

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
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('25-supervisor.ts') || process.argv[1]?.endsWith('25-supervisor.js')) {
  main().catch(console.error);
}
