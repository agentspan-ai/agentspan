/**
 * State Machine -- order processing workflow as an explicit state machine.
 *
 * Demonstrates:
 *   - Modeling a real-world process as a formal state machine
 *   - Each node transitions the entity to the next legal state
 *   - Status tracking in state with timestamps
 *   - Practical use case: e-commerce order processing pipeline
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
interface StatusLog {
  status: string;
  timestamp: string;
  note: string;
}

const OrderState = Annotation.Root({
  order_id: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  items: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
  customer: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  current_status: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => 'NEW',
  }),
  status_history: Annotation<StatusLog[]>({
    reducer: (_prev: StatusLog[], next: StatusLog[]) => next ?? _prev,
    default: () => [],
  }),
  shipping_address: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  tracking_number: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  summary: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof OrderState.State;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function log(state: State, status: string, note: string): Partial<State> {
  const history = [...(state.status_history || [])];
  history.push({
    status,
    timestamp: new Date().toISOString(),
    note,
  });
  return { current_status: status, status_history: history };
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function validateOrder(state: State): Partial<State> {
  const items = state.items || [];
  if (items.length === 0 || !state.customer) {
    return { ...log(state, 'VALIDATION_FAILED', 'Missing items or customer'), tracking_number: '' };
  }
  return log(state, 'VALIDATED', `Order contains ${items.length} item(s)`);
}

async function paymentProcessing(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage('Simulate a payment approval. Respond with APPROVED or DECLINED.'),
    new HumanMessage(`Customer: ${state.customer}, Items: ${(state.items || []).join(', ')}`),
  ]);

  const content = typeof response.content === 'string' ? response.content : '';
  if (content.toUpperCase().includes('DECLINED')) {
    return log(state, 'PAYMENT_FAILED', 'Payment declined');
  }
  return log(state, 'PAYMENT_APPROVED', 'Payment processed successfully');
}

function prepareShipment(state: State): Partial<State> {
  // Simple hash-like tracking number
  let hash = 0;
  for (const ch of state.order_id) {
    hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  }
  const tracking = `TRK${String(Math.abs(hash) % 10000000).padStart(7, '0')}`;
  return {
    ...log(state, 'PREPARING_SHIPMENT', `Assigned tracking: ${tracking}`),
    tracking_number: tracking,
  };
}

function shipOrder(state: State): Partial<State> {
  return log(state, 'SHIPPED', `Package dispatched to ${state.shipping_address || 'customer address'}`);
}

function deliverOrder(state: State): Partial<State> {
  return log(state, 'DELIVERED', 'Package delivered successfully');
}

function generateSummary(state: State): Partial<State> {
  const historyText = (state.status_history || [])
    .map((e) => `  [${e.timestamp}] ${e.status}: ${e.note}`)
    .join('\n');
  const summary =
    `Order ${state.order_id} — Final Status: ${state.current_status}\n` +
    `Customer: ${state.customer}\n` +
    `Items: ${(state.items || []).join(', ')}\n` +
    `Tracking: ${state.tracking_number || 'N/A'}\n\n` +
    `Status History:\n${historyText}`;
  return { summary };
}

// ---------------------------------------------------------------------------
// Routing functions
// ---------------------------------------------------------------------------
function routeAfterValidation(state: State): string {
  return state.current_status === 'VALIDATED' ? 'payment' : 'done';
}

function routeAfterPayment(state: State): string {
  return state.current_status === 'PAYMENT_APPROVED' ? 'prepare' : 'done';
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(OrderState);
builder.addNode('validate', validateOrder);
builder.addNode('payment', paymentProcessing);
builder.addNode('prepare', prepareShipment);
builder.addNode('ship', shipOrder);
builder.addNode('deliver', deliverOrder);
builder.addNode('summarize', generateSummary);

builder.addEdge(START, 'validate');
builder.addConditionalEdges('validate', routeAfterValidation, {
  payment: 'payment',
  done: 'summarize',
});
builder.addConditionalEdges('payment', routeAfterPayment, {
  prepare: 'prepare',
  done: 'summarize',
});
builder.addEdge('prepare', 'ship');
builder.addEdge('ship', 'deliver');
builder.addEdge('deliver', 'summarize');
builder.addEdge('summarize', END);

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
    const result = await runtime.run(
    graph,
    JSON.stringify({
    order_id: 'ORD-2025-001',
    items: ['Python Book', 'Mechanical Keyboard', 'USB-C Hub'],
    customer: 'Alice Smith',
    shipping_address: '123 Main St, San Francisco, CA 94105',
    current_status: 'NEW',
    status_history: [],
    tracking_number: '',
    summary: '',
    }),
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents state_machine
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('38-state-machine.ts') || process.argv[1]?.endsWith('38-state-machine.js')) {
  main().catch(console.error);
}
