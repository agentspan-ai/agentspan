/**
 * Document Grader -- score document relevance for a query.
 *
 * Demonstrates:
 *   - Grading a batch of documents against a query
 *   - Filtering to only relevant documents
 *   - Generating a final answer citing sources
 *   - Practical use case: search result re-ranking and citation-based Q&A
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// Sample document corpus
// ---------------------------------------------------------------------------
interface Doc {
  pageContent: string;
  metadata: { id: number; title: string };
}

const CORPUS: Doc[] = [
  {
    pageContent:
      'Python is a high-level, general-purpose programming language known for its readability.',
    metadata: { id: 1, title: 'Python Overview' },
  },
  {
    pageContent: 'The Eiffel Tower is located in Paris and was built in 1889.',
    metadata: { id: 2, title: 'Eiffel Tower' },
  },
  {
    pageContent:
      'Python supports multiple programming paradigms including procedural, OOP, and functional programming.',
    metadata: { id: 3, title: 'Python Paradigms' },
  },
  {
    pageContent:
      'Machine learning is a subset of AI that enables systems to learn from data.',
    metadata: { id: 4, title: 'Machine Learning' },
  },
  {
    pageContent:
      'Python has a rich ecosystem of scientific libraries: NumPy, pandas, matplotlib, and scikit-learn.',
    metadata: { id: 5, title: 'Python Science Stack' },
  },
  {
    pageContent: 'The Great Wall of China stretches over 13,000 miles.',
    metadata: { id: 6, title: 'Great Wall' },
  },
];

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
interface ScoreEntry {
  doc_id: number;
  title: string;
  score: number;
}

const GraderState = Annotation.Root({
  query: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  documents: Annotation<Doc[]>({
    reducer: (_prev: Doc[], next: Doc[]) => next ?? _prev,
    default: () => [],
  }),
  scores: Annotation<ScoreEntry[]>({
    reducer: (_prev: ScoreEntry[], next: ScoreEntry[]) => next ?? _prev,
    default: () => [],
  }),
  relevant_docs: Annotation<Doc[]>({
    reducer: (_prev: Doc[], next: Doc[]) => next ?? _prev,
    default: () => [],
  }),
  answer: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof GraderState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function retrieveAll(_state: State): Partial<State> {
  return { documents: CORPUS };
}

async function gradeDocuments(state: State): Promise<Partial<State>> {
  const scores: ScoreEntry[] = [];

  for (const doc of state.documents) {
    const response = await llm.invoke([
      new SystemMessage(
        'Score the relevance of the document to the query from 1 (not relevant) to 5 (highly relevant). ' +
          'Respond with only a single integer.',
      ),
      new HumanMessage(`Query: ${state.query}\n\nDocument: ${doc.pageContent}`),
    ]);

    const content = typeof response.content === 'string' ? response.content.trim() : '';
    let score = 1;
    try {
      score = parseInt(content[0], 10) || 1;
    } catch {
      score = 1;
    }

    scores.push({ doc_id: doc.metadata.id, title: doc.metadata.title, score });
  }

  const relevant = state.documents.filter((_doc, i) => scores[i].score >= 3);
  return { scores, relevant_docs: relevant };
}

async function generateAnswer(state: State): Promise<Partial<State>> {
  const relevant = state.relevant_docs || [];
  if (relevant.length === 0) {
    return { answer: 'No relevant documents found for this query.' };
  }

  const context = relevant
    .map((doc) => `[${doc.metadata.title}]: ${doc.pageContent}`)
    .join('\n');

  const response = await llm.invoke([
    new SystemMessage(
      'Answer the question using only the provided sources. ' +
        'Cite the source title in brackets when using information from it.',
    ),
    new HumanMessage(`Query: ${state.query}\n\nSources:\n${context}`),
  ]);

  const content = typeof response.content === 'string' ? response.content.trim() : '';
  return { answer: content };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(GraderState);
builder.addNode('retrieve', retrieveAll);
builder.addNode('grade', gradeDocuments);
builder.addNode('generate', generateAnswer);

builder.addEdge(START, 'retrieve');
builder.addEdge('retrieve', 'grade');
builder.addEdge('grade', 'generate');
builder.addEdge('generate', END);

const graph = builder.compile();

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
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(graph);
    await runtime.serve(graph);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // graph,
    // 'What are the main features and uses of Python?',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('37-document-grader.ts') || process.argv[1]?.endsWith('37-document-grader.js')) {
  main().catch(console.error);
}
