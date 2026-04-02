/**
 * Classify and Route -- LLM-based input classification with specialized routing.
 *
 * Demonstrates:
 *   - Using an LLM to classify input into a discrete category
 *   - Conditional edges routing to specialized handler nodes
 *   - Each handler node is tailored to its domain
 *   - Practical use case: smart help desk that routes to the right department
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
const ClassifyState = Annotation.Root({
  input: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  category: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  answer: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof ClassifyState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function classify(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'Classify the input into exactly one category. ' +
        'Categories: science, history, sports, technology, cooking. ' +
        'Respond with the category name only.',
    ),
    new HumanMessage(state.input),
  ]);
  return { category: String(response.content).trim().toLowerCase() };
}

async function answerScience(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('You are a science expert. Answer precisely with relevant scientific context.'),
    new HumanMessage(state.input),
  ]);
  return { answer: `[Science Expert] ${String(response.content).trim()}` };
}

async function answerHistory(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('You are a history expert. Provide historical context and key dates.'),
    new HumanMessage(state.input),
  ]);
  return { answer: `[History Expert] ${String(response.content).trim()}` };
}

async function answerSports(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('You are a sports analyst. Give stats and context when relevant.'),
    new HumanMessage(state.input),
  ]);
  return { answer: `[Sports Analyst] ${String(response.content).trim()}` };
}

async function answerTechnology(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('You are a technology expert. Be clear and technically accurate.'),
    new HumanMessage(state.input),
  ]);
  return { answer: `[Tech Expert] ${String(response.content).trim()}` };
}

async function answerCooking(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('You are a professional chef. Give practical, delicious advice.'),
    new HumanMessage(state.input),
  ]);
  return { answer: `[Chef] ${String(response.content).trim()}` };
}

function route(state: State): string {
  const mapping: Record<string, string> = {
    science: 'science',
    history: 'history',
    sports: 'sports',
    technology: 'technology',
    cooking: 'cooking',
  };
  return mapping[state.category || ''] || 'technology'; // default to technology
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(ClassifyState);
builder.addNode('classify', classify);
builder.addNode('science', answerScience);
builder.addNode('history', answerHistory);
builder.addNode('sports', answerSports);
builder.addNode('technology', answerTechnology);
builder.addNode('cooking', answerCooking);

builder.addEdge(START, 'classify');
builder.addConditionalEdges('classify', route, {
  science: 'science',
  history: 'history',
  sports: 'sports',
  technology: 'technology',
  cooking: 'cooking',
});
builder.addEdge('science', END);
builder.addEdge('history', END);
builder.addEdge('sports', END);
builder.addEdge('technology', END);
builder.addEdge('cooking', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'What is photosynthesis?';

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
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents classify_and_route
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('31-classify-and-route.ts') || process.argv[1]?.endsWith('31-classify-and-route.js')) {
  main().catch(console.error);
}
