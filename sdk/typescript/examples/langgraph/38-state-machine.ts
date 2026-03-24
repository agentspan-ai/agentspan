/**
 * State Machine -- order processing workflow as an explicit state machine.
 *
 * Demonstrates:
 *   - Modeling a real-world process as a formal state machine
 *   - Each node transitions the entity to the next legal state
 *   - Status tracking in state with timestamps
 *   - Practical use case: e-commerce order processing pipeline
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("validate", routeAfterValidation, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------
interface StatusLog {
  status: string;
  timestamp: string;
  note: string;
}

interface OrderState {
  orderId: string;
  items: string[];
  customer: string;
  currentStatus: string;
  statusHistory: StatusLog[];
  shippingAddress: string;
  trackingNumber: string;
  summary: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function log(state: OrderState, status: string, note: string): Partial<OrderState> {
  const history = [...(state.statusHistory ?? [])];
  history.push({
    status,
    timestamp: new Date().toISOString(),
    note,
  });
  return { currentStatus: status, statusHistory: history };
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function validateOrder(state: OrderState): Partial<OrderState> {
  if (!state.items?.length || !state.customer) {
    return { ...log(state, 'VALIDATION_FAILED', 'Missing items or customer'), trackingNumber: '' };
  }
  return log(state, 'VALIDATED', `Order contains ${state.items.length} item(s)`);
}

function paymentProcessing(state: OrderState): Partial<OrderState> {
  // Simulate payment approval
  return log(state, 'PAYMENT_APPROVED', 'Payment processed successfully');
}

function prepareShipment(state: OrderState): Partial<OrderState> {
  const hash = state.orderId.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const tracking = `TRK${String(hash % 10_000_000).padStart(7, '0')}`;
  return {
    ...log(state, 'PREPARING_SHIPMENT', `Assigned tracking: ${tracking}`),
    trackingNumber: tracking,
  };
}

function shipOrder(state: OrderState): Partial<OrderState> {
  return log(state, 'SHIPPED', `Package dispatched to ${state.shippingAddress || 'customer address'}`);
}

function deliverOrder(state: OrderState): Partial<OrderState> {
  return log(state, 'DELIVERED', 'Package delivered successfully');
}

function generateSummary(state: OrderState): Partial<OrderState> {
  const historyText = state.statusHistory
    .map((e) => `  [${e.timestamp}] ${e.status}: ${e.note}`)
    .join('\n');

  const summary =
    `Order ${state.orderId} -- Final Status: ${state.currentStatus}\n` +
    `Customer: ${state.customer}\n` +
    `Items: ${state.items.join(', ')}\n` +
    `Tracking: ${state.trackingNumber || 'N/A'}\n\n` +
    `Status History:\n${historyText}`;

  return { summary };
}

function routeAfterValidation(state: OrderState): string {
  return state.currentStatus === 'VALIDATED' ? 'payment' : 'done';
}

function routeAfterPayment(state: OrderState): string {
  return state.currentStatus === 'PAYMENT_APPROVED' ? 'prepare' : 'done';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'order_state_machine',

  invoke: async (input: Record<string, unknown>) => {
    let state: OrderState = {
      orderId: 'ORD-2025-001',
      items: ['Python Book', 'Mechanical Keyboard', 'USB-C Hub'],
      customer: 'Alice Smith',
      shippingAddress: '123 Main St, San Francisco, CA 94105',
      currentStatus: 'NEW',
      statusHistory: [],
      trackingNumber: '',
      summary: '',
    };

    state = { ...state, ...validateOrder(state) };
    if (routeAfterValidation(state) === 'payment') {
      state = { ...state, ...paymentProcessing(state) };
      if (routeAfterPayment(state) === 'prepare') {
        state = { ...state, ...prepareShipment(state) };
        state = { ...state, ...shipOrder(state) };
        state = { ...state, ...deliverOrder(state) };
      }
    }
    state = { ...state, ...generateSummary(state) };

    return { output: state.summary };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['validate', {}],
      ['payment', {}],
      ['prepare', {}],
      ['ship', {}],
      ['deliver', {}],
      ['summarize', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'validate'],
      // Conditional: validate -> payment | summarize
      // Conditional: payment -> prepare | summarize
      ['prepare', 'ship'],
      ['ship', 'deliver'],
      ['deliver', 'summarize'],
      ['summarize', '__end__'],
    ],
  }),

  nodes: new Map([
    ['validate', {}],
    ['payment', {}],
    ['prepare', {}],
    ['ship', {}],
    ['deliver', {}],
    ['summarize', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    let state: OrderState = {
      orderId: 'ORD-2025-001',
      items: ['Python Book', 'Mechanical Keyboard', 'USB-C Hub'],
      customer: 'Alice Smith',
      shippingAddress: '123 Main St, San Francisco, CA 94105',
      currentStatus: 'NEW',
      statusHistory: [],
      trackingNumber: '',
      summary: '',
    };

    state = { ...state, ...validateOrder(state) };
    yield ['updates', { validate: { currentStatus: state.currentStatus } }];

    if (routeAfterValidation(state) === 'payment') {
      state = { ...state, ...paymentProcessing(state) };
      yield ['updates', { payment: { currentStatus: state.currentStatus } }];

      if (routeAfterPayment(state) === 'prepare') {
        state = { ...state, ...prepareShipment(state) };
        yield ['updates', { prepare: { trackingNumber: state.trackingNumber } }];

        state = { ...state, ...shipOrder(state) };
        yield ['updates', { ship: { currentStatus: state.currentStatus } }];

        state = { ...state, ...deliverOrder(state) };
        yield ['updates', { deliver: { currentStatus: state.currentStatus } }];
      }
    }

    state = { ...state, ...generateSummary(state) };
    yield ['updates', { summarize: { summary: state.summary } }];
    yield ['values', { output: state.summary }];
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
      'Process order ORD-2025-001',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
