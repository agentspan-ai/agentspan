/**
 * Output Validator -- validate LLM output and retry until it meets criteria.
 *
 * Demonstrates:
 *   - Generating structured output (JSON) and validating it against a schema
 *   - Looping back to regenerate if validation fails
 *   - Tracking validation attempts in state to prevent infinite loops
 *   - Practical use case: ensuring the LLM always returns valid JSON
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

const MAX_ATTEMPTS = 4;
const REQUIRED_FIELDS = ['name', 'age', 'occupation', 'hobby'];

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
const ValidatorState = Annotation.Root({
  prompt: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  raw_output: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  validation_error: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  attempts: Annotation<number>({
    reducer: (_prev: number, next: number) => next ?? _prev,
    default: () => 0,
  }),
  valid_data: Annotation<Record<string, any> | null>({
    reducer: (
      _prev: Record<string, any> | null,
      next: Record<string, any> | null,
    ) => next !== undefined ? next : _prev,
    default: () => null,
  }),
});

type State = typeof ValidatorState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function generateProfile(state: State): Promise<Partial<State>> {
  const attempt = (state.attempts || 0) + 1;
  let errorHint = '';
  if (state.validation_error) {
    errorHint = `\n\nPrevious attempt failed validation: ${state.validation_error}. Please fix this.`;
  }

  const response = await llm.invoke([
    new SystemMessage(
      'Generate a fictional person profile as a JSON object with exactly these fields: ' +
        'name (string), age (integer), occupation (string), hobby (string). ' +
        'Return ONLY valid JSON -- no markdown, no backticks, no explanation.' +
        errorHint,
    ),
    new HumanMessage(state.prompt),
  ]);
  return { raw_output: String(response.content).trim(), attempts: attempt };
}

function validateOutput(state: State): Partial<State> {
  let raw = state.raw_output || '';

  // Strip markdown code fences if present
  if (raw.includes('```')) {
    const parts = raw.split('```');
    raw = parts[1] || raw;
    if (raw.startsWith('json')) raw = raw.slice(4);
  }

  let data: Record<string, any>;
  try {
    data = JSON.parse(raw.trim());
  } catch (e: any) {
    return { validation_error: `JSON parse error: ${e.message}`, valid_data: null };
  }

  const missing = REQUIRED_FIELDS.filter((f) => !(f in data));
  if (missing.length > 0) {
    return { validation_error: `Missing fields: ${missing.join(', ')}`, valid_data: null };
  }

  if (typeof data.age !== 'number' || !Number.isInteger(data.age)) {
    return { validation_error: "Field 'age' must be an integer", valid_data: null };
  }

  return { validation_error: '', valid_data: data };
}

function shouldRetry(state: State): string {
  if (state.validation_error && (state.attempts || 0) < MAX_ATTEMPTS) return 'retry';
  return 'done';
}

function finalize(state: State): Partial<State> {
  if (state.valid_data) {
    const d = state.valid_data;
    const summary =
      `Valid profile generated:\n` +
      `  Name:       ${d.name}\n` +
      `  Age:        ${d.age}\n` +
      `  Occupation: ${d.occupation}\n` +
      `  Hobby:      ${d.hobby}\n` +
      `  (Attempts:  ${state.attempts || 1})`;
    return { raw_output: summary };
  }
  return {
    raw_output: `Failed to generate valid output after ${state.attempts || 1} attempts.`,
  };
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(ValidatorState);
builder.addNode('generate', generateProfile);
builder.addNode('validate', validateOutput);
builder.addNode('finalize', finalize);

builder.addEdge(START, 'generate');
builder.addEdge('generate', 'validate');
builder.addConditionalEdges('validate', shouldRetry, {
  retry: 'generate',
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

const PROMPT = 'Create a fictional software engineer from Japan';

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
if (process.argv[1]?.endsWith('33-output-validator.ts') || process.argv[1]?.endsWith('33-output-validator.js')) {
  main().catch(console.error);
}
