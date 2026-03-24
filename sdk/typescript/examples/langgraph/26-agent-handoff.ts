/**
 * Agent Handoff -- transferring control between specialized agents.
 *
 * Demonstrates:
 *   - Explicit handoff from a triage agent to a specialist
 *   - Using state flags to control which agent is active
 *   - Each specialist has its own focused prompt and tools
 *   - Practical use case: customer service triage -> billing / technical / general
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("triage", routeToSpecialist, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface HandoffState {
  userMessage: string;
  category: string;
  response: string;
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function triage(state: HandoffState): Partial<HandoffState> {
  const msg = state.userMessage.toLowerCase();
  let category = 'general';
  if (msg.includes('charg') || msg.includes('bill') || msg.includes('subscri') || msg.includes('payment')) {
    category = 'billing';
  } else if (msg.includes('crash') || msg.includes('error') || msg.includes('bug') || msg.includes('fault')) {
    category = 'technical';
  }
  return { category };
}

function billingAgent(state: HandoffState): Partial<HandoffState> {
  return {
    response:
      `[Billing Agent] Thank you for reaching out about your billing concern. ` +
      `I can see the issue and will process a resolution. You should see the ` +
      `adjustment on your next statement.`,
  };
}

function technicalAgent(state: HandoffState): Partial<HandoffState> {
  return {
    response:
      `[Technical Support] I understand you're experiencing a technical issue. ` +
      `Please try the following: 1) Restart the application, 2) Clear your cache, ` +
      `3) Update to the latest version. If the issue persists, please provide logs.`,
  };
}

function generalAgent(state: HandoffState): Partial<HandoffState> {
  return {
    response:
      `[General Support] I'd be happy to help you with that request. ` +
      `Please allow 1-2 business days for the change to take effect.`,
  };
}

function routeToSpecialist(state: HandoffState): string {
  const cat = state.category ?? 'general';
  if (cat.includes('billing')) return 'billing';
  if (cat.includes('technical')) return 'technical';
  return 'general';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'agent_handoff',

  invoke: async (input: Record<string, unknown>) => {
    const userMessage = (input.input as string) ?? '';
    let state: HandoffState = { userMessage, category: '', response: '' };

    state = { ...state, ...triage(state) };

    const dest = routeToSpecialist(state);
    if (dest === 'billing') state = { ...state, ...billingAgent(state) };
    else if (dest === 'technical') state = { ...state, ...technicalAgent(state) };
    else state = { ...state, ...generalAgent(state) };

    return { output: state.response };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['triage', {}],
      ['billing', {}],
      ['technical', {}],
      ['general', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'triage'],
      // Conditional: triage -> billing | technical | general
      ['billing', '__end__'],
      ['technical', '__end__'],
      ['general', '__end__'],
    ],
  }),

  nodes: new Map([
    ['triage', {}],
    ['billing', {}],
    ['technical', {}],
    ['general', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const userMessage = (input.input as string) ?? '';
    let state: HandoffState = { userMessage, category: '', response: '' };

    state = { ...state, ...triage(state) };
    yield ['updates', { triage: { category: state.category } }];

    const dest = routeToSpecialist(state);
    if (dest === 'billing') {
      state = { ...state, ...billingAgent(state) };
      yield ['updates', { billing: { response: state.response } }];
    } else if (dest === 'technical') {
      state = { ...state, ...technicalAgent(state) };
      yield ['updates', { technical: { response: state.response } }];
    } else {
      state = { ...state, ...generalAgent(state) };
      yield ['updates', { general: { response: state.response } }];
    }

    yield ['values', { output: state.response }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const queries = [
    'I was charged twice for my subscription this month.',
    'My application keeps crashing with a segmentation fault.',
    'Can I change my account email address?',
  ];

  const runtime = new AgentRuntime();
  try {
    for (const query of queries) {
      console.log(`\nQuery: ${query}`);
      const result = await runtime.run(graph, query);
      console.log('Status:', result.status);
      result.printResult();
      console.log('-'.repeat(60));
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
