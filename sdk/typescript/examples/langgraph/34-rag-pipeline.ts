/**
 * RAG Pipeline -- Retrieval-Augmented Generation with a StateGraph.
 *
 * Demonstrates:
 *   - A retrieve -> grade -> generate pipeline
 *   - In-memory document store with simple keyword retrieval (no vector DB needed)
 *   - Grading retrieved documents for relevance before generation
 *   - Re-querying with a rewritten question if documents are not relevant
 *   - Practical use case: Q&A over a private knowledge base
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '@conductoross/conductor-agent-sdk';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// In-memory knowledge base
// ---------------------------------------------------------------------------
interface Document {
  pageContent: string;
  metadata: Record<string, string>;
}

const DOCUMENTS: Document[] = [
  {
    pageContent:
      'LangGraph is a library for building stateful, multi-actor applications with LLMs. ' +
      'It extends LangChain with the ability to coordinate multiple chains (or actors) ' +
      'across multiple steps of computation in a cyclic manner.',
    metadata: { source: 'langgraph_docs', topic: 'langgraph' },
  },
  {
    pageContent:
      'LangChain provides tools for building applications powered by language models. ' +
      'It includes components for prompt management, chains, agents, memory, and retrieval. ' +
      'The LCEL (LangChain Expression Language) allows composing pipelines with the | operator.',
    metadata: { source: 'langchain_docs', topic: 'langchain' },
  },
  {
    pageContent:
      'Agentspan provides a runtime for deploying LangGraph and LangChain agents at scale. ' +
      'It uses Conductor as an orchestration engine and exposes agents as Conductor tasks. ' +
      'The AgentRuntime class handles worker registration and lifecycle management.',
    metadata: { source: 'agentspan_docs', topic: 'agentspan' },
  },
  {
    pageContent:
      'Vector databases store high-dimensional embeddings for semantic similarity search. ' +
      'Popular options include Pinecone, Weaviate, Chroma, and FAISS. ' +
      'They are commonly used in RAG pipelines to retrieve relevant context.',
    metadata: { source: 'vector_db_docs', topic: 'databases' },
  },
];

function keywordRetrieve(query: string, topK: number = 2): Document[] {
  const queryWords = new Set(query.toLowerCase().split(/\s+/));
  const scored: Array<[number, Document]> = [];
  for (const doc of DOCUMENTS) {
    const docWords = new Set(doc.pageContent.toLowerCase().split(/\s+/));
    let score = 0;
    for (const w of queryWords) {
      if (docWords.has(w)) score++;
    }
    scored.push([score, doc]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return scored
    .filter(([score]) => score > 0)
    .slice(0, topK)
    .map(([, doc]) => doc);
}

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const RAGState = Annotation.Root({
  question: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  rewritten_question: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  documents: Annotation<Document[]>({
    reducer: (_prev: Document[], next: Document[]) => next ?? _prev,
    default: () => [],
  }),
  relevant_docs: Annotation<Document[]>({
    reducer: (_prev: Document[], next: Document[]) => next ?? _prev,
    default: () => [],
  }),
  generation: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  attempts: Annotation<number>({
    reducer: (_prev: number, next: number) => next ?? _prev,
    default: () => 0,
  }),
});

type State = typeof RAGState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function retrieve(state: State): Partial<State> {
  const query = state.rewritten_question || state.question;
  const docs = keywordRetrieve(query);
  return { documents: docs, attempts: (state.attempts || 0) + 1 };
}

async function gradeDocuments(state: State): Promise<Partial<State>> {
  const question = state.question;
  const relevant: Document[] = [];
  for (const doc of state.documents || []) {
    const response = await llm.invoke([
      new SystemMessage(
        'Determine if the document is relevant to the question. ' +
          "Reply with 'yes' or 'no' only.",
      ),
      new HumanMessage(`Question: ${question}\n\nDocument: ${doc.pageContent}`),
    ]);
    if (String(response.content).toLowerCase().includes('yes')) {
      relevant.push(doc);
    }
  }
  return { relevant_docs: relevant };
}

async function rewriteQuestion(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'Rewrite this question to be more specific for document retrieval. Return only the rewritten question.',
    ),
    new HumanMessage(state.question),
  ]);
  return { rewritten_question: String(response.content).trim() };
}

async function generateAnswer(state: State): Promise<Partial<State>> {
  const docs = (state.relevant_docs && state.relevant_docs.length > 0)
    ? state.relevant_docs
    : state.documents || [];
  let context = docs.map((d) => d.pageContent).join('\n\n');
  if (!context) context = 'No relevant documents found.';

  const response = await llm.invoke([
    new SystemMessage(
      'You are a helpful assistant. Answer the question based on the provided context. ' +
        "If the context doesn't contain enough information, say so.",
    ),
    new HumanMessage(`Context:\n${context}\n\nQuestion: ${state.question}`),
  ]);
  return { generation: String(response.content).trim() };
}

function decideToGenerate(state: State): string {
  if (state.relevant_docs && state.relevant_docs.length > 0) return 'generate';
  if ((state.attempts || 0) >= 2) return 'generate'; // generate anyway after 2 attempts
  return 'rewrite';
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const graph = new StateGraph(RAGState)
  .addNode('retrieve', retrieve)
  .addNode('grade', gradeDocuments)
  .addNode('rewrite', rewriteQuestion)
  .addNode('generate', generateAnswer)
  .addEdge(START, 'retrieve')
  .addEdge('retrieve', 'grade')
  .addConditionalEdges('grade', decideToGenerate, {
    generate: 'generate',
    rewrite: 'rewrite',
  })
  .addEdge('rewrite', 'retrieve')
  .addEdge('generate', END)
  .compile({ name: "rag_pipeline" });

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'anthropic/claude-sonnet-4-6',
  framework: 'langgraph',
};

const PROMPT = 'What is LangGraph and how does it differ from LangChain?';

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
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents rag_pipeline
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
