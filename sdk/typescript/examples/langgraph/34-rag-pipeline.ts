/**
 * RAG Pipeline -- Retrieval-Augmented Generation with a StateGraph.
 *
 * Demonstrates:
 *   - A retrieve -> grade -> generate pipeline
 *   - In-memory document store with simple keyword retrieval
 *   - Grading retrieved documents for relevance before generation
 *   - Re-querying with a rewritten question if documents are not relevant
 *   - Practical use case: Q&A over a private knowledge base
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   import { Document } from '@langchain/core/documents';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Document type and in-memory knowledge base
// ---------------------------------------------------------------------------
interface Document {
  content: string;
  metadata: { source: string; topic: string };
}

const DOCUMENTS: Document[] = [
  {
    content:
      'LangGraph is a library for building stateful, multi-actor applications with LLMs. ' +
      'It extends LangChain with the ability to coordinate multiple chains (or actors) ' +
      'across multiple steps of computation in a cyclic manner.',
    metadata: { source: 'langgraph_docs', topic: 'langgraph' },
  },
  {
    content:
      'LangChain provides tools for building applications powered by language models. ' +
      'It includes components for prompt management, chains, agents, memory, and retrieval. ' +
      'The LCEL (LangChain Expression Language) allows composing pipelines with the | operator.',
    metadata: { source: 'langchain_docs', topic: 'langchain' },
  },
  {
    content:
      'Agentspan provides a runtime for deploying LangGraph and LangChain agents at scale. ' +
      'It uses Conductor as an orchestration engine and exposes agents as Conductor tasks. ' +
      'The AgentRuntime class handles worker registration and lifecycle management.',
    metadata: { source: 'agentspan_docs', topic: 'agentspan' },
  },
  {
    content:
      'Vector databases store high-dimensional embeddings for semantic similarity search. ' +
      'Popular options include Pinecone, Weaviate, Chroma, and FAISS. ' +
      'They are commonly used in RAG pipelines to retrieve relevant context.',
    metadata: { source: 'vector_db_docs', topic: 'databases' },
  },
];

function keywordRetrieve(query: string, topK: number = 2): Document[] {
  const queryWords = new Set(query.toLowerCase().split(/\s+/));
  const scored: [number, Document][] = DOCUMENTS.map((doc) => {
    const docWords = new Set(doc.content.toLowerCase().split(/\s+/));
    const overlap = [...queryWords].filter((w) => docWords.has(w)).length;
    return [overlap, doc];
  });
  scored.sort((a, b) => b[0] - a[0]);
  return scored.filter(([s]) => s > 0).slice(0, topK).map(([, d]) => d);
}

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface RAGState {
  question: string;
  rewrittenQuestion: string | null;
  documents: Document[];
  relevantDocs: Document[];
  generation: string;
  attempts: number;
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function retrieve(state: RAGState): Partial<RAGState> {
  const query = state.rewrittenQuestion ?? state.question;
  const docs = keywordRetrieve(query);
  return { documents: docs, attempts: (state.attempts ?? 0) + 1 };
}

function gradeDocs(state: RAGState): Partial<RAGState> {
  // Simple relevance grading: check keyword overlap with question
  const qWords = new Set(state.question.toLowerCase().split(/\s+/));
  const relevant = state.documents.filter((doc) => {
    const docWords = new Set(doc.content.toLowerCase().split(/\s+/));
    const overlap = [...qWords].filter((w) => docWords.has(w)).length;
    return overlap >= 2;
  });
  return { relevantDocs: relevant };
}

function rewriteQuestion(state: RAGState): Partial<RAGState> {
  return {
    rewrittenQuestion: `${state.question} framework library features capabilities`,
  };
}

function generateAnswer(state: RAGState): Partial<RAGState> {
  const docs = state.relevantDocs.length > 0 ? state.relevantDocs : state.documents;
  if (docs.length === 0) {
    return { generation: 'No relevant documents found for this query.' };
  }

  const context = docs.map((d) => d.content).join('\n\n');
  const generation =
    `Based on the retrieved documents:\n\n` +
    `${context}\n\n` +
    `Answer: LangGraph extends LangChain with stateful, multi-actor orchestration ` +
    `capabilities, while LangChain provides the core components for prompt management, ` +
    `chains, agents, and retrieval. LangGraph adds cyclic graph computation on top of ` +
    `LangChain's linear chain model.`;
  return { generation };
}

function decideToGenerate(state: RAGState): string {
  if (state.relevantDocs.length > 0) return 'generate';
  if ((state.attempts ?? 0) >= 2) return 'generate';
  return 'rewrite';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'rag_pipeline',

  invoke: async (input: Record<string, unknown>) => {
    const question = (input.input as string) ?? '';
    let state: RAGState = {
      question,
      rewrittenQuestion: null,
      documents: [],
      relevantDocs: [],
      generation: '',
      attempts: 0,
    };

    for (let i = 0; i < 3; i++) {
      state = { ...state, ...retrieve(state) };
      state = { ...state, ...gradeDocs(state) };

      const decision = decideToGenerate(state);
      if (decision === 'generate') {
        state = { ...state, ...generateAnswer(state) };
        break;
      }
      state = { ...state, ...rewriteQuestion(state) };
    }

    return { output: state.generation };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['retrieve', {}],
      ['grade', {}],
      ['rewrite', {}],
      ['generate', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'retrieve'],
      ['retrieve', 'grade'],
      // Conditional: grade -> generate | rewrite
      ['rewrite', 'retrieve'],
      ['generate', '__end__'],
    ],
  }),

  nodes: new Map([
    ['retrieve', {}],
    ['grade', {}],
    ['rewrite', {}],
    ['generate', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const question = (input.input as string) ?? '';
    let state: RAGState = {
      question,
      rewrittenQuestion: null,
      documents: [],
      relevantDocs: [],
      generation: '',
      attempts: 0,
    };

    for (let i = 0; i < 3; i++) {
      state = { ...state, ...retrieve(state) };
      yield ['updates', { retrieve: { documents: state.documents.length } }];

      state = { ...state, ...gradeDocs(state) };
      yield ['updates', { grade: { relevantDocs: state.relevantDocs.length } }];

      const decision = decideToGenerate(state);
      if (decision === 'generate') {
        state = { ...state, ...generateAnswer(state) };
        yield ['updates', { generate: { generation: state.generation } }];
        break;
      }
      state = { ...state, ...rewriteQuestion(state) };
      yield ['updates', { rewrite: { rewrittenQuestion: state.rewrittenQuestion } }];
    }

    yield ['values', { output: state.generation }];
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
      'What is LangGraph and how does it differ from LangChain?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
