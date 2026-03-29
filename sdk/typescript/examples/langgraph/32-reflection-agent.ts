/**
 * Reflection Agent -- self-critique and iterative improvement.
 *
 * Demonstrates:
 *   - A generate -> reflect -> improve loop
 *   - Stopping when the critic judges the output acceptable or after max rounds
 *   - How to track iteration count in state
 *   - Practical use case: essay generation with quality self-improvement
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0.3 });

const MAX_ITERATIONS = 3;

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const ReflectionState = Annotation.Root({
  topic: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  draft: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  critique: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  iterations: Annotation<number>({
    reducer: (_prev: number, next: number) => next ?? _prev,
    default: () => 0,
  }),
  final_output: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof ReflectionState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function generate(state: State): Promise<Partial<State>> {
  const iterations = state.iterations || 0;
  let prompt: string;

  if (iterations === 0) {
    prompt = `Write a concise, well-structured paragraph about: ${state.topic}`;
  } else {
    prompt =
      `Improve this paragraph about '${state.topic}' based on the critique below.\n\n` +
      `Current draft:\n${state.draft}\n\n` +
      `Critique:\n${state.critique}\n\n` +
      'Return only the improved paragraph.';
  }

  const response = await llm.invoke([
    new SystemMessage('You are a skilled writer. Produce clear, engaging prose.'),
    new HumanMessage(prompt),
  ]);
  return { draft: String(response.content).trim(), iterations: iterations + 1 };
}

async function reflect(state: State): Promise<Partial<State>> {
  const response = await llm.invoke([
    new SystemMessage(
      'You are a rigorous editor. Critique the paragraph on:\n' +
        '1. Clarity\n2. Accuracy\n3. Engagement\n4. Conciseness\n\n' +
        "If the paragraph is already excellent, start your response with 'APPROVE'. " +
        "Otherwise start with 'REVISE' and list specific improvements.",
    ),
    new HumanMessage(`Topic: ${state.topic}\n\nParagraph:\n${state.draft}`),
  ]);
  return { critique: String(response.content).trim() };
}

function shouldContinue(state: State): string {
  if ((state.iterations || 0) >= MAX_ITERATIONS) return 'done';
  const critique = state.critique || '';
  if (critique.toUpperCase().startsWith('APPROVE')) return 'done';
  return 'improve';
}

function finalize(state: State): Partial<State> {
  return { final_output: state.draft };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(ReflectionState);
builder.addNode('generate', generate);
builder.addNode('reflect', reflect);
builder.addNode('finalize', finalize);

builder.addEdge(START, 'generate');
builder.addEdge('generate', 'reflect');
builder.addConditionalEdges('reflect', shouldContinue, {
  improve: 'generate',
  done: 'finalize',
});
builder.addEdge('finalize', END);

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'the importance of open-source software in modern technology';

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
if (process.argv[1]?.endsWith('32-reflection-agent.ts') || process.argv[1]?.endsWith('32-reflection-agent.js')) {
  main().catch(console.error);
}
