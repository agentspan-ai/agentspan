/**
 * Customer Support Router -- StateGraph with greet -> classify -> route -> respond.
 *
 * Demonstrates:
 *   - Multi-node StateGraph with conditional branching
 *   - Classifying user intent and routing to specialized handlers
 *   - Billing, technical, and general support branches
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const SupportState = Annotation.Root({
  user_message: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  greeting: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  category: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  response: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof SupportState.State;

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function greet(_state: State): Partial<State> {
  return {
    greeting:
      'Hello! Thank you for contacting our support team. ' +
      "I'm here to help you today.",
  };
}

async function classify(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      "Classify the customer message into exactly one category: " +
        "'billing', 'technical', or 'general'. " +
        "Return only the single category word.",
    ),
    new HumanMessage(state.user_message),
  ]);
  let category = (response.content as string).trim().toLowerCase();
  if (!['billing', 'technical', 'general'].includes(category)) {
    category = 'general';
  }
  return { category };
}

function routeCategory(state: State): string {
  return state.category;
}

async function handleBilling(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a billing specialist. The customer has a billing question. ' +
        'Be empathetic, offer to review their account, and explain payment options clearly.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { response: `${state.greeting}\n\n${response.content}` };
}

async function handleTechnical(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a technical support engineer. The customer has a technical issue. ' +
        'Provide step-by-step troubleshooting guidance. Be clear and concise.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { response: `${state.greeting}\n\n${response.content}` };
}

async function handleGeneral(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a helpful customer service agent handling general inquiries. ' +
        'Be friendly, informative, and direct. Offer additional help at the end.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { response: `${state.greeting}\n\n${response.content}` };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(SupportState);
builder.addNode('greet', greet);
builder.addNode('classify', classify);
builder.addNode('billing', handleBilling);
builder.addNode('technical', handleTechnical);
builder.addNode('general', handleGeneral);

builder.addEdge(START, 'greet');
builder.addEdge('greet', 'classify');
builder.addConditionalEdges('classify', routeCategory, {
  billing: 'billing',
  technical: 'technical',
  general: 'general',
});
builder.addEdge('billing', END);
builder.addEdge('technical', END);
builder.addEdge('general', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT =
  'I was charged twice for my subscription this month and need a refund.';

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
if (process.argv[1]?.endsWith('11-customer-support.ts') || process.argv[1]?.endsWith('11-customer-support.js')) {
  main().catch(console.error);
}
