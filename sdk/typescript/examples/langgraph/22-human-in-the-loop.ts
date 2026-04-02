/**
 * Human-in-the-Loop -- draft -> human review -> approve/revise conditional workflow.
 *
 * Demonstrates:
 *   - Draft -> Human Review -> Approve/Revise conditional workflow
 *   - A simulated human review step that pauses execution for input
 *   - Conditional routing based on human verdict
 *   - LLM nodes for drafting and revising content
 *
 * Note: In the TypeScript SDK the human_task decorator is not yet available.
 * This example simulates the human review step with a mock function that
 * auto-approves. In production, this would integrate with the AgentSpan UI
 * or API for real human-in-the-loop review.
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const EmailState = Annotation.Root({
  request: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  draft: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  review_verdict: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  review_feedback: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  final_email: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof EmailState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function draftEmail(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a professional email writer. Draft a concise, polite email. ' +
        'Include a subject line, greeting, body, and sign-off.',
    ),
    new HumanMessage(`Request: ${state.request}`),
  ]);
  return { draft: (response.content as string).trim() };
}

function reviewEmail(state: State): Partial<State> {
  /**
   * Simulated human review step.
   *
   * In production this would be a Conductor HUMAN task that pauses execution
   * and waits for a human to approve or reject the draft via the AgentSpan
   * UI or API. For this example we auto-approve.
   */
  return {
    review_verdict: 'APPROVE',
    review_feedback: 'Looks good, no changes needed.',
  };
}

function routeAfterReview(state: State): string {
  if ((state.review_verdict ?? '').toUpperCase() === 'APPROVE') {
    return 'finalize';
  }
  return 'revise';
}

function finalize(state: State): Partial<State> {
  return { final_email: state.draft };
}

async function reviseEmail(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a professional email writer. Revise this email draft ' +
        "to address the reviewer's feedback. Keep the same intent but improve quality.",
    ),
    new HumanMessage(
      `Original request: ${state.request ?? ''}\n\n` +
        `Current draft:\n${state.draft}\n\n` +
        `Reviewer feedback: ${state.review_feedback ?? 'Needs improvement.'}`,
    ),
  ]);
  return { final_email: (response.content as string).trim() };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(EmailState);
builder.addNode('draft_node', draftEmail);
builder.addNode('review', reviewEmail);
builder.addNode('finalize', finalize);
builder.addNode('revise', reviseEmail);

builder.addEdge(START, 'draft_node');
builder.addEdge('draft_node', 'review');
builder.addConditionalEdges('review', routeAfterReview, {
  finalize: 'finalize',
  revise: 'revise',
});
builder.addEdge('finalize', END);
builder.addEdge('revise', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT =
  'Schedule a team meeting for next Monday at 10am to discuss Q3 plans.';

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
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents human_in_the_loop
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('22-human-in-the-loop.ts') || process.argv[1]?.endsWith('22-human-in-the-loop.js')) {
  main().catch(console.error);
}
