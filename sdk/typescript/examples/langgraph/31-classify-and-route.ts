/**
 * Classify and Route -- LLM-based input classification with specialized routing.
 *
 * Demonstrates:
 *   - Using an LLM to classify input into a discrete category
 *   - Conditional edges routing to specialized handler nodes
 *   - Each handler node is tailored to its domain
 *   - Practical use case: smart help desk that routes to the right department
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("classify", route, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface ClassifyState {
  input: string;
  category: string;
  answer: string;
}

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function classify(state: ClassifyState): Partial<ClassifyState> {
  const q = state.input.toLowerCase();
  let category = 'technology'; // default
  if (q.includes('photosynth') || q.includes('atom') || q.includes('gravity') || q.includes('cell'))
    category = 'science';
  else if (q.includes('war') || q.includes('ancient') || q.includes('history') || q.includes('century'))
    category = 'history';
  else if (q.includes('tennis') || q.includes('football') || q.includes('olympic') || q.includes('sport'))
    category = 'sports';
  else if (q.includes('kubernetes') || q.includes('programming') || q.includes('software') || q.includes('api'))
    category = 'technology';
  else if (q.includes('risotto') || q.includes('cook') || q.includes('recipe') || q.includes('bake'))
    category = 'cooking';
  return { category };
}

function answerScience(state: ClassifyState): Partial<ClassifyState> {
  return {
    answer: `[Science Expert] Photosynthesis is the process by which plants convert light energy, ` +
      `usually from the sun, into chemical energy stored in glucose. It takes place primarily in ` +
      `the chloroplasts using chlorophyll and involves two stages: the light-dependent reactions ` +
      `and the Calvin cycle.`,
  };
}

function answerHistory(state: ClassifyState): Partial<ClassifyState> {
  return {
    answer: `[History Expert] World War II ended in 1945. Germany surrendered on May 8 (V-E Day), ` +
      `and Japan surrendered on August 15 following the atomic bombings, with the formal ceremony ` +
      `on September 2, 1945 (V-J Day).`,
  };
}

function answerSports(state: ClassifyState): Partial<ClassifyState> {
  return {
    answer: `[Sports Analyst] As of 2024, Novak Djokovic holds the record for the most Grand Slam ` +
      `singles titles in men's tennis with 24 titles. Margaret Court holds the all-time record ` +
      `with 24 singles titles in the Open Era combined with pre-Open Era wins.`,
  };
}

function answerTechnology(state: ClassifyState): Partial<ClassifyState> {
  return {
    answer: `[Tech Expert] Kubernetes is an open-source container orchestration platform originally ` +
      `developed by Google. It automates the deployment, scaling, and management of containerized ` +
      `applications across clusters of machines.`,
  };
}

function answerCooking(state: ClassifyState): Partial<ClassifyState> {
  return {
    answer: `[Chef] For a perfect risotto: toast Arborio rice in butter, deglaze with white wine, ` +
      `then add warm stock one ladle at a time, stirring constantly. Finish with Parmigiano-Reggiano ` +
      `and a knob of cold butter for creaminess. Total time: about 20 minutes.`,
  };
}

function route(state: ClassifyState): string {
  const mapping: Record<string, string> = {
    science: 'science',
    history: 'history',
    sports: 'sports',
    technology: 'technology',
    cooking: 'cooking',
  };
  return mapping[state.category] ?? 'technology';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'classify_and_route_agent',

  invoke: async (input: Record<string, unknown>) => {
    const userInput = (input.input as string) ?? '';
    let state: ClassifyState = { input: userInput, category: '', answer: '' };

    state = { ...state, ...classify(state) };

    const dest = route(state);
    const handlers: Record<string, (s: ClassifyState) => Partial<ClassifyState>> = {
      science: answerScience,
      history: answerHistory,
      sports: answerSports,
      technology: answerTechnology,
      cooking: answerCooking,
    };
    state = { ...state, ...(handlers[dest] ?? answerTechnology)(state) };

    return { output: state.answer };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['classify', {}],
      ['science', {}],
      ['history', {}],
      ['sports', {}],
      ['technology', {}],
      ['cooking', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'classify'],
      // Conditional: classify -> science | history | sports | technology | cooking
      ['science', '__end__'],
      ['history', '__end__'],
      ['sports', '__end__'],
      ['technology', '__end__'],
      ['cooking', '__end__'],
    ],
  }),

  nodes: new Map([
    ['classify', {}],
    ['science', {}],
    ['history', {}],
    ['sports', {}],
    ['technology', {}],
    ['cooking', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const userInput = (input.input as string) ?? '';
    let state: ClassifyState = { input: userInput, category: '', answer: '' };

    state = { ...state, ...classify(state) };
    yield ['updates', { classify: { category: state.category } }];

    const dest = route(state);
    const handlers: Record<string, (s: ClassifyState) => Partial<ClassifyState>> = {
      science: answerScience,
      history: answerHistory,
      sports: answerSports,
      technology: answerTechnology,
      cooking: answerCooking,
    };
    state = { ...state, ...(handlers[dest] ?? answerTechnology)(state) };
    yield ['updates', { [dest]: { answer: state.answer } }];

    yield ['values', { output: state.answer }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const questions = [
    'What is photosynthesis?',
    'When did World War II end?',
    'Who has won the most Grand Slam tennis titles?',
    'What is Kubernetes?',
    'How do I make a perfect risotto?',
  ];

  const runtime = new AgentRuntime();
  try {
    for (const q of questions) {
      console.log(`\nQ: ${q}`);
      const result = await runtime.run(graph, q);
      result.printResult();
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
