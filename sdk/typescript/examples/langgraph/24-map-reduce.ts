/**
 * Map-Reduce -- fan-out to parallel workers then aggregate results.
 *
 * Demonstrates:
 *   - Fan-out pattern for parallel processing via Send API
 *   - Processing multiple items concurrently
 *   - Reducing parallel results into a single final answer
 *   - Practical use case: analyzing multiple documents simultaneously
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   import { Send } from '@langchain/langgraph';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------
interface OverallState {
  topic: string;
  documents: string[];
  summaries: string[];
  finalReport: string;
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function generateDocuments(state: OverallState): Partial<OverallState> {
  // Mock: generate 3 document snippets about the topic
  const docs = [
    `Solar panel efficiency has surpassed 30% in lab conditions, with perovskite cells leading the way. Commercial deployment costs have dropped 89% since 2010.`,
    `Wind energy capacity additions reached 117 GW globally in 2024. Offshore wind is seeing rapid growth, particularly in Northern Europe and Asia Pacific.`,
    `Battery storage technology breakthroughs include solid-state batteries with 500 Wh/kg energy density. Grid-scale storage installations doubled year-over-year.`,
  ];
  return { documents: docs };
}

function summarizeDoc(doc: string, topic: string): string {
  // Mock: summarize a single document
  const words = doc.split(' ').slice(0, 8).join(' ');
  return `Summary of "${words}...": Key developments in ${topic} sector.`;
}

function fanOutAndSummarize(state: OverallState): Partial<OverallState> {
  // Process each document (in production, these would be parallel via Send)
  const summaries = state.documents.map((doc) =>
    summarizeDoc(doc, state.topic),
  );
  return { summaries };
}

function reduceSummaries(state: OverallState): Partial<OverallState> {
  const bulletPoints = state.summaries.map((s) => `  - ${s}`).join('\n');
  const finalReport =
    `Final Report on "${state.topic}":\n` +
    `Analyzed ${state.documents.length} documents.\n\n` +
    `Key Findings:\n${bulletPoints}\n\n` +
    `Conclusion: Significant progress across all renewable energy sectors with ` +
    `cost reductions and efficiency improvements driving rapid adoption.`;
  return { finalReport };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'map_reduce_agent',

  invoke: async (input: Record<string, unknown>) => {
    const topic = (input.input as string) ?? '';
    let state: OverallState = {
      topic,
      documents: [],
      summaries: [],
      finalReport: '',
    };

    state = { ...state, ...generateDocuments(state) };
    state = { ...state, ...fanOutAndSummarize(state) };
    state = { ...state, ...reduceSummaries(state) };

    return { output: state.finalReport };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['generate_documents', {}],
      ['summarize_doc', {}],
      ['reduce', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'generate_documents'],
      ['generate_documents', 'summarize_doc'],
      ['summarize_doc', 'reduce'],
      ['reduce', '__end__'],
    ],
  }),

  nodes: new Map([
    ['generate_documents', {}],
    ['summarize_doc', {}],
    ['reduce', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const topic = (input.input as string) ?? '';
    let state: OverallState = {
      topic,
      documents: [],
      summaries: [],
      finalReport: '',
    };

    state = { ...state, ...generateDocuments(state) };
    yield ['updates', { generate_documents: { documents: state.documents } }];

    state = { ...state, ...fanOutAndSummarize(state) };
    yield ['updates', { summarize_doc: { summaries: state.summaries } }];

    state = { ...state, ...reduceSummaries(state) };
    yield ['updates', { reduce: { finalReport: state.finalReport } }];

    yield ['values', { output: state.finalReport }];
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
      'renewable energy breakthroughs in 2024',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
