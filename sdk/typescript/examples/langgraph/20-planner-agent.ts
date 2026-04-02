/**
 * Planner Agent -- StateGraph with plan -> execute_steps -> review pipeline.
 *
 * Demonstrates:
 *   - A three-stage planning agent: LLM creates a plan, executes each step, then reviews
 *   - Iterating over dynamically generated plan steps in the state
 *   - Using Annotation with a list of steps and accumulated results
 *   - Practical use case: project breakdown and task execution
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const PlannerState = Annotation.Root({
  goal: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  steps: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
  step_results: Annotation<string[]>({
    reducer: (_prev: string[], next: string[]) => next ?? _prev,
    default: () => [],
  }),
  review: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof PlannerState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function plan(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      "You are a project planner. Break the user's goal into 3-5 concrete, " +
        'actionable steps. Return ONLY a JSON array of step strings. ' +
        'Example: ["Step 1: ...", "Step 2: ..."]',
    ),
    new HumanMessage(`Goal: ${state.goal}`),
  ]);

  let raw = (response.content as string).trim();
  let steps: string[];
  try {
    // Handle markdown code blocks
    if (raw.includes('```')) {
      raw = raw.split('```')[1];
      if (raw.startsWith('json')) {
        raw = raw.slice(4);
      }
    }
    const parsed = JSON.parse(raw.trim());
    steps = Array.isArray(parsed) ? parsed : [raw];
  } catch {
    // Fallback: split by newlines
    steps = raw
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }

  return { steps: steps.slice(0, 5), step_results: [] };
}

async function executeSteps(state: State): Promise<Partial<State>> {
  const results: string[] = [...(state.step_results ?? [])];

  for (const step of state.steps) {
    const response = await llm.invoke([
      new SystemMessage(
        'You are an expert executor. Complete the following task step ' +
          'in the context of the overall goal. Provide a concise result (2-3 sentences).',
      ),
      new HumanMessage(`Goal: ${state.goal}\nStep to execute: ${step}`),
    ]);
    results.push(`[${step}]\n${(response.content as string).trim()}`);
  }

  return { step_results: results };
}

async function review(state: State): Promise<Partial<State>> {
  const stepsSummary = state.step_results.join('\n\n');
  const response = await llm.invoke([
    new SystemMessage(
      'You are a quality reviewer. Given the goal and the results of each execution step, ' +
        'write a concise final review that:\n' +
        '1) Confirms whether the goal was achieved\n' +
        '2) Highlights the most important outcomes\n' +
        '3) Notes any gaps or next actions needed',
    ),
    new HumanMessage(
      `Goal: ${state.goal}\n\nStep Results:\n${stepsSummary}`,
    ),
  ]);
  return { review: response.content as string };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(PlannerState);
builder.addNode('plan', plan);
builder.addNode('execute', executeSteps);
builder.addNode('review_node', review);

builder.addEdge(START, 'plan');
builder.addEdge('plan', 'execute');
builder.addEdge('execute', 'review_node');
builder.addEdge('review_node', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT =
  'Launch a new open-source Python library for data validation.';

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
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents planner_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('20-planner-agent.ts') || process.argv[1]?.endsWith('20-planner-agent.js')) {
  main().catch(console.error);
}
