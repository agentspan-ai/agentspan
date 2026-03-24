/**
 * Output Validator -- validate LLM output and retry until it meets criteria.
 *
 * Demonstrates:
 *   - Generating structured output (JSON) and validating against a schema
 *   - Looping back to regenerate if validation fails
 *   - Tracking validation attempts in state to prevent infinite loops
 *   - Practical use case: ensuring the LLM always returns valid JSON
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("validate", shouldRetry, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface ValidatorState {
  prompt: string;
  rawOutput: string;
  validationError: string | null;
  attempts: number;
  validData: Record<string, unknown> | null;
}

const MAX_ATTEMPTS = 4;
const REQUIRED_FIELDS = new Set(['name', 'age', 'occupation', 'hobby']);

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function generateProfile(state: ValidatorState): Partial<ValidatorState> {
  const attempt = (state.attempts ?? 0) + 1;

  // Simulate: first attempt might produce bad JSON, subsequent ones are correct
  let rawOutput: string;
  if (attempt === 1 && Math.random() < 0.3) {
    rawOutput = '{"name": "Yuki Tanaka", "age": "thirty", "occupation": "software engineer"}';
  } else {
    rawOutput = JSON.stringify({
      name: 'Yuki Tanaka',
      age: 29,
      occupation: 'Software Engineer',
      hobby: 'Origami',
    });
  }

  return { rawOutput, attempts: attempt };
}

function validateOutput(state: ValidatorState): Partial<ValidatorState> {
  let raw = state.rawOutput ?? '';

  // Strip markdown code fences if present
  if (raw.includes('```')) {
    const parts = raw.split('```');
    raw = parts[1] ?? raw;
    if (raw.startsWith('json')) raw = raw.slice(4);
  }

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(raw.trim());
  } catch (e) {
    return { validationError: `JSON parse error: ${e}`, validData: null };
  }

  const missing = [...REQUIRED_FIELDS].filter((f) => !(f in data));
  if (missing.length > 0) {
    return { validationError: `Missing fields: ${missing.join(', ')}`, validData: null };
  }

  if (typeof data.age !== 'number') {
    return { validationError: "Field 'age' must be an integer", validData: null };
  }

  return { validationError: null, validData: data };
}

function shouldRetry(state: ValidatorState): string {
  if (state.validationError && (state.attempts ?? 0) < MAX_ATTEMPTS) return 'retry';
  return 'done';
}

function finalize(state: ValidatorState): Partial<ValidatorState> {
  if (state.validData) {
    const d = state.validData;
    const summary =
      `Valid profile generated:\n` +
      `  Name:       ${d.name}\n` +
      `  Age:        ${d.age}\n` +
      `  Occupation: ${d.occupation}\n` +
      `  Hobby:      ${d.hobby}\n` +
      `  (Attempts:  ${state.attempts ?? 1})`;
    return { rawOutput: summary };
  }
  return { rawOutput: `Failed to generate valid output after ${state.attempts ?? 1} attempts.` };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'output_validator_agent',

  invoke: async (input: Record<string, unknown>) => {
    const prompt = (input.input as string) ?? '';
    let state: ValidatorState = {
      prompt,
      rawOutput: '',
      validationError: null,
      attempts: 0,
      validData: null,
    };

    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      state = { ...state, ...generateProfile(state) };
      state = { ...state, ...validateOutput(state) };
      if (shouldRetry(state) === 'done') break;
    }

    state = { ...state, ...finalize(state) };
    return { output: state.rawOutput };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['generate', {}],
      ['validate', {}],
      ['finalize', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'generate'],
      ['generate', 'validate'],
      // Conditional: validate -> generate (retry) | finalize (done)
      ['finalize', '__end__'],
    ],
  }),

  nodes: new Map([
    ['generate', {}],
    ['validate', {}],
    ['finalize', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const prompt = (input.input as string) ?? '';
    let state: ValidatorState = {
      prompt,
      rawOutput: '',
      validationError: null,
      attempts: 0,
      validData: null,
    };

    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      state = { ...state, ...generateProfile(state) };
      yield ['updates', { generate: { rawOutput: state.rawOutput, attempts: state.attempts } }];

      state = { ...state, ...validateOutput(state) };
      yield ['updates', { validate: { validationError: state.validationError, validData: state.validData } }];

      if (shouldRetry(state) === 'done') break;
    }

    state = { ...state, ...finalize(state) };
    yield ['updates', { finalize: { rawOutput: state.rawOutput } }];
    yield ['values', { output: state.rawOutput }];
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
      'Create a fictional software engineer from Japan',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
