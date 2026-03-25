/**
 * Subgraph -- composing graphs within graphs.
 *
 * Demonstrates:
 *   - Building a nested subgraph for a specific subtask
 *   - Connecting a subgraph as a node in a parent graph
 *   - Passing state between parent graph and subgraph
 *   - Practical use case: document processing pipeline with a nested analysis subgraph
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// Subgraph state schema
// ---------------------------------------------------------------------------
const AnalysisState = Annotation.Root({
  text: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  sentiment: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  keywords: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
  summary: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type AnalysisStateType = typeof AnalysisState.State;

// ---------------------------------------------------------------------------
// Subgraph node functions
// ---------------------------------------------------------------------------
async function analyzeSentiment(state: AnalysisStateType): Promise<Partial<AnalysisStateType>> {
  const response = await llm.invoke([
    new SystemMessage(
      'Classify the sentiment of the text. Return ONLY: positive, negative, or neutral.',
    ),
    new HumanMessage(state.text),
  ]);
  return { sentiment: (response.content as string).trim().toLowerCase() };
}

async function extractKeywords(state: AnalysisStateType): Promise<Partial<AnalysisStateType>> {
  const response = await llm.invoke([
    new SystemMessage(
      'Extract 3-5 keywords from the text. Return a comma-separated list only.',
    ),
    new HumanMessage(state.text),
  ]);
  const keywords = (response.content as string).split(',').map((k) => k.trim());
  return { keywords };
}

async function summarizeText(state: AnalysisStateType): Promise<Partial<AnalysisStateType>> {
  const response = await llm.invoke([
    new SystemMessage('Summarize this text in one sentence.'),
    new HumanMessage(state.text),
  ]);
  return { summary: (response.content as string).trim() };
}

// ---------------------------------------------------------------------------
// Build the subgraph
// ---------------------------------------------------------------------------
const analysisBuilder = new StateGraph(AnalysisState);
analysisBuilder.addNode('sentiment_node', analyzeSentiment);
analysisBuilder.addNode('keywords_node', extractKeywords);
analysisBuilder.addNode('summarize', summarizeText);
analysisBuilder.addEdge(START, 'sentiment_node');
analysisBuilder.addEdge('sentiment_node', 'keywords_node');
analysisBuilder.addEdge('keywords_node', 'summarize');
analysisBuilder.addEdge('summarize', END);
const analysisSubgraph = analysisBuilder.compile();

// ---------------------------------------------------------------------------
// Parent graph state schema
// ---------------------------------------------------------------------------
const DocumentState = Annotation.Root({
  document: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  analysis_text: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  sentiment: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  keywords: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
  summary: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  report: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type DocumentStateType = typeof DocumentState.State;

// ---------------------------------------------------------------------------
// Parent graph node functions
// ---------------------------------------------------------------------------
function prepare(state: DocumentStateType): Partial<DocumentStateType> {
  // Use the whole document as the analysis text
  return { analysis_text: state.document };
}

async function runAnalysis(state: DocumentStateType): Promise<Partial<DocumentStateType>> {
  const result = await analysisSubgraph.invoke({ text: state.analysis_text });
  return {
    sentiment: result.sentiment ?? '',
    keywords: result.keywords ?? [],
    summary: result.summary ?? '',
  };
}

function buildReport(state: DocumentStateType): Partial<DocumentStateType> {
  const keywordsStr = (state.keywords ?? []).join(', ');
  const report =
    'Document Analysis Report\n' +
    '========================\n' +
    `Sentiment:  ${state.sentiment ?? 'unknown'}\n` +
    `Keywords:   ${keywordsStr}\n` +
    `Summary:    ${state.summary ?? ''}`;
  return { report };
}

// ---------------------------------------------------------------------------
// Build the parent graph
// ---------------------------------------------------------------------------
const parentBuilder = new StateGraph(DocumentState);
parentBuilder.addNode('prepare', prepare);
parentBuilder.addNode('analysis', runAnalysis);
parentBuilder.addNode('build_report', buildReport);
parentBuilder.addEdge(START, 'prepare');
parentBuilder.addEdge('prepare', 'analysis');
parentBuilder.addEdge('analysis', 'build_report');
parentBuilder.addEdge('build_report', END);

const graph = parentBuilder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT =
  'LangGraph makes it easy to build stateful, multi-actor applications with LLMs. ' +
  'The framework provides first-class support for persistence, streaming, and human-in-the-loop ' +
  'workflows. Developers love its flexibility and the ability to compose complex pipelines ' +
  'using simple Python functions.';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
