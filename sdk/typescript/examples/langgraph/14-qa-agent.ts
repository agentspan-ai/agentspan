/**
 * QA Agent -- StateGraph that retrieves context then generates an answer.
 *
 * Demonstrates:
 *   - Two-stage pipeline: retrieve context, then generate answer
 *   - Mocked retrieval step that returns relevant passages
 *   - Grounded answer generation using retrieved context
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// Mock document store (simulates a vector DB retrieval)
// ---------------------------------------------------------------------------
const DOCS: Record<string, string[]> = {
  python: [
    'Python is a high-level, interpreted programming language created by Guido van Rossum in 1991.',
    'Python emphasizes code readability and uses significant indentation.',
    'The Python Package Index (PyPI) hosts over 450,000 packages as of 2024.',
  ],
  'machine learning': [
    'Machine learning is a subset of AI that enables systems to learn from data without explicit programming.',
    'Supervised learning uses labeled datasets; unsupervised learning finds hidden patterns.',
    'Neural networks inspired by the brain are the foundation of deep learning.',
  ],
  kubernetes: [
    'Kubernetes (K8s) is an open-source container orchestration system developed by Google.',
    'It automates deployment, scaling, and management of containerized applications.',
    'Kubernetes uses Pods as the smallest deployable unit.',
  ],
};

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const QAState = Annotation.Root({
  question: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  context: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  answer: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof QAState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function retrieveContext(state: State): Partial<State> {
  const questionLower = state.question.toLowerCase();
  const passages: string[] = [];
  for (const [topic, docs] of Object.entries(DOCS)) {
    if (questionLower.includes(topic)) {
      passages.push(...docs);
    }
  }
  if (passages.length === 0) {
    // Fallback: return first doc from each topic
    for (const docs of Object.values(DOCS)) {
      passages.push(docs[0]);
    }
  }
  const context = passages.map((p) => `- ${p}`).join('\n');
  return { context };
}

async function generateAnswer(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a knowledgeable assistant. Answer the question using ONLY ' +
        'the provided context. If the context does not contain enough information, ' +
        'say so clearly. Be concise and accurate.\n\n' +
        `Context:\n${state.context}`,
    ),
    new HumanMessage(state.question),
  ]);
  return { answer: response.content as string };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(QAState);
builder.addNode('retrieve', retrieveContext);
builder.addNode('generate', generateAnswer);

builder.addEdge(START, 'retrieve');
builder.addEdge('retrieve', 'generate');
builder.addEdge('generate', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'What is Python and how many packages does it have?';

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
if (process.argv[1]?.endsWith('14-qa-agent.ts') || process.argv[1]?.endsWith('14-qa-agent.js')) {
  main().catch(console.error);
}
