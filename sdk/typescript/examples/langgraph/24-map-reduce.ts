/**
 * Map-Reduce -- fan-out to parallel workers then aggregate results.
 *
 * Demonstrates:
 *   - Using Send for fan-out (parallel list accumulation)
 *   - Processing multiple items concurrently via the Send API
 *   - Reducing parallel results into a single final answer
 *   - Practical use case: analyzing multiple documents simultaneously
 */

import { StateGraph, START, END, Annotation, Send } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schemas
// ---------------------------------------------------------------------------
const OverallState = Annotation.Root({
  topic: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  documents: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
  summaries: Annotation<string[]>({
    reducer: (prev: string[], next: string[]) => [...prev, ...next],
    default: () => [],
  }),
  final_report: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type OverallStateType = typeof OverallState.State;

const DocumentState = Annotation.Root({
  document: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  topic: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  summaries: Annotation<string[]>({
    reducer: (prev: string[], next: string[]) => [...prev, ...next],
    default: () => [],
  }),
});

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function generateDocuments(state: OverallStateType): Promise<Partial<OverallStateType>> {
  const response = await llm.invoke([
    new SystemMessage(
      'Generate 3 short text snippets (each 2-3 sentences) about the given topic. ' +
        'Format as a numbered list:\n1. ...\n2. ...\n3. ...',
    ),
    new HumanMessage(`Topic: ${state.topic}`),
  ]);
  const content = String(response.content).trim();
  const lines = content
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  const docs = lines
    .filter((l) => /^\d/.test(l))
    .map((l) => l.replace(/^\d+\.\s*/, ''))
    .slice(0, 3);
  return { documents: docs.length > 0 ? docs : [content] };
}

function fanOut(state: OverallStateType): Send[] {
  return state.documents.map(
    (doc) => new Send('summarize_doc', { document: doc, topic: state.topic, summaries: [] }),
  );
}

async function summarizeDoc(
  state: typeof DocumentState.State,
): Promise<{ summaries: string[] }> {
  const response = await llm.invoke([
    new SystemMessage('Summarize this text in one concise sentence.'),
    new HumanMessage(`Topic: ${state.topic}\n\nText: ${state.document}`),
  ]);
  return { summaries: [String(response.content).trim()] };
}

async function reduceSummaries(state: OverallStateType): Promise<Partial<OverallStateType>> {
  const bulletPoints = state.summaries.map((s) => `- ${s}`).join('\n');
  const response = await llm.invoke([
    new SystemMessage(
      'You are a report writer. Given the topic and a list of summaries, ' +
        'write a cohesive 2-3 sentence final report.',
    ),
    new HumanMessage(`Topic: ${state.topic}\n\nSummaries:\n${bulletPoints}`),
  ]);
  return { final_report: String(response.content).trim() };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(OverallState);
builder.addNode('generate_documents', generateDocuments);
builder.addNode('summarize_doc', summarizeDoc);
builder.addNode('reduce', reduceSummaries);

builder.addEdge(START, 'generate_documents');
builder.addConditionalEdges('generate_documents', fanOut, ['summarize_doc']);
builder.addEdge('summarize_doc', 'reduce');
builder.addEdge('reduce', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'renewable energy breakthroughs in 2024';

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
if (process.argv[1]?.endsWith('24-map-reduce.ts') || process.argv[1]?.endsWith('24-map-reduce.js')) {
  main().catch(console.error);
}
