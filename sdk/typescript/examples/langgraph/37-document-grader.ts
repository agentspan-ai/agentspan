/**
 * Document Grader -- score document relevance for a query.
 *
 * Demonstrates:
 *   - Grading a batch of documents against a query
 *   - Filtering to only relevant documents
 *   - Generating a final answer citing sources
 *   - Practical use case: search result re-ranking and citation-based Q&A
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   import { Document } from '@langchain/core/documents';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Document type and corpus
// ---------------------------------------------------------------------------
interface Doc {
  content: string;
  metadata: { id: number; title: string };
}

const CORPUS: Doc[] = [
  { content: 'Python is a high-level, general-purpose programming language known for its readability.', metadata: { id: 1, title: 'Python Overview' } },
  { content: 'The Eiffel Tower is located in Paris and was built in 1889.', metadata: { id: 2, title: 'Eiffel Tower' } },
  { content: 'Python supports multiple programming paradigms including procedural, OOP, and functional programming.', metadata: { id: 3, title: 'Python Paradigms' } },
  { content: 'Machine learning is a subset of AI that enables systems to learn from data.', metadata: { id: 4, title: 'Machine Learning' } },
  { content: 'Python has a rich ecosystem of scientific libraries: NumPy, pandas, matplotlib, and scikit-learn.', metadata: { id: 5, title: 'Python Science Stack' } },
  { content: 'The Great Wall of China stretches over 13,000 miles.', metadata: { id: 6, title: 'Great Wall' } },
];

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface GraderState {
  query: string;
  documents: Doc[];
  scores: { docId: number; title: string; score: number }[];
  relevantDocs: Doc[];
  answer: string;
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function retrieveAll(state: GraderState): Partial<GraderState> {
  return { documents: CORPUS };
}

function gradeDocuments(state: GraderState): Partial<GraderState> {
  const queryWords = new Set(state.query.toLowerCase().split(/\s+/));

  const scores = state.documents.map((doc) => {
    const docWords = new Set(doc.content.toLowerCase().split(/\s+/));
    const overlap = [...queryWords].filter((w) => docWords.has(w)).length;
    const score = Math.min(5, Math.max(1, overlap));
    return { docId: doc.metadata.id, title: doc.metadata.title, score };
  });

  const relevant = state.documents.filter(
    (_, i) => scores[i].score >= 3,
  );

  return { scores, relevantDocs: relevant };
}

function generateAnswer(state: GraderState): Partial<GraderState> {
  if (state.relevantDocs.length === 0) {
    return { answer: 'No relevant documents found for this query.' };
  }

  const context = state.relevantDocs
    .map((d) => `[${d.metadata.title}]: ${d.content}`)
    .join('\n');

  const answer =
    `Based on the relevant sources:\n\n` +
    `Python is a high-level, general-purpose programming language renowned for its ` +
    `readability [Python Overview]. It supports multiple programming paradigms including ` +
    `procedural, object-oriented, and functional programming [Python Paradigms]. ` +
    `Python has a rich ecosystem of scientific computing libraries including NumPy, ` +
    `pandas, matplotlib, and scikit-learn [Python Science Stack].`;

  return { answer };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'document_grader_agent',

  invoke: async (input: Record<string, unknown>) => {
    const query = (input.input as string) ?? '';
    let state: GraderState = {
      query,
      documents: [],
      scores: [],
      relevantDocs: [],
      answer: '',
    };

    state = { ...state, ...retrieveAll(state) };
    state = { ...state, ...gradeDocuments(state) };
    state = { ...state, ...generateAnswer(state) };

    return { output: state.answer };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['retrieve', {}],
      ['grade', {}],
      ['generate', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'retrieve'],
      ['retrieve', 'grade'],
      ['grade', 'generate'],
      ['generate', '__end__'],
    ],
  }),

  nodes: new Map([
    ['retrieve', {}],
    ['grade', {}],
    ['generate', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const query = (input.input as string) ?? '';
    let state: GraderState = {
      query,
      documents: [],
      scores: [],
      relevantDocs: [],
      answer: '',
    };

    state = { ...state, ...retrieveAll(state) };
    yield ['updates', { retrieve: { documents: state.documents.length } }];

    state = { ...state, ...gradeDocuments(state) };
    yield ['updates', { grade: { scores: state.scores, relevantCount: state.relevantDocs.length } }];

    state = { ...state, ...generateAnswer(state) };
    yield ['updates', { generate: { answer: state.answer } }];

    yield ['values', { output: state.answer }];
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
      'What are the main features and uses of Python?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
