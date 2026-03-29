/**
 * Agent Handoff -- transferring control between specialized agents.
 *
 * Demonstrates:
 *   - Explicit handoff from a triage agent to a specialist
 *   - Using state flags to control which agent is active
 *   - Each specialist has its own focused prompt
 *   - Practical use case: customer service triage -> billing / technical / general routing
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const HandoffState = Annotation.Root({
  user_message: Annotation<string>({
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

type State = typeof HandoffState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function triage(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'Classify the customer message into exactly one category. ' +
        'Respond with a single word: billing, technical, or general.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { category: String(response.content).trim().toLowerCase() };
}

async function billingAgent(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      "You are a billing specialist. Answer the customer's billing question " +
        'professionally and helpfully. Keep it under 3 sentences.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { response: `[Billing Agent] ${String(response.content).trim()}` };
}

async function technicalAgent(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a technical support specialist. Troubleshoot the issue step by step. ' +
        'Provide clear, actionable guidance in under 4 sentences.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { response: `[Technical Support] ${String(response.content).trim()}` };
}

async function generalAgent(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a friendly general customer service agent. ' +
        'Help the customer with their question warmly and concisely.',
    ),
    new HumanMessage(state.user_message),
  ]);
  return { response: `[General Support] ${String(response.content).trim()}` };
}

function routeToSpecialist(state: State): string {
  const category = state.category || 'general';
  if (category.includes('billing')) return 'billing';
  if (category.includes('technical') || category.includes('tech')) return 'technical';
  return 'general';
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(HandoffState);
builder.addNode('triage', triage);
builder.addNode('billing', billingAgent);
builder.addNode('technical', technicalAgent);
builder.addNode('general', generalAgent);

builder.addEdge(START, 'triage');
builder.addConditionalEdges('triage', routeToSpecialist, {
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

const PROMPT = 'I was charged twice for my subscription this month.';

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
if (process.argv[1]?.endsWith('26-agent-handoff.ts') || process.argv[1]?.endsWith('26-agent-handoff.js')) {
  main().catch(console.error);
}
