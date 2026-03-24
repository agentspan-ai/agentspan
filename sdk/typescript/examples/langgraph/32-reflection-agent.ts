/**
 * Reflection Agent -- self-critique and iterative improvement.
 *
 * Demonstrates:
 *   - A generate -> reflect -> improve loop
 *   - Stopping when the critic judges the output acceptable or after max rounds
 *   - How to track iteration count in state
 *   - Practical use case: essay generation with quality self-improvement
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("reflect", shouldContinue, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State type
// ---------------------------------------------------------------------------
interface ReflectionState {
  topic: string;
  draft: string;
  critique: string;
  iterations: number;
  finalOutput: string;
}

const MAX_ITERATIONS = 3;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function generate(state: ReflectionState): Partial<ReflectionState> {
  const iterations = (state.iterations ?? 0) + 1;
  let draft: string;

  if (iterations === 1) {
    draft =
      `Open-source software has become the backbone of modern technology. From Linux powering ` +
      `the majority of servers worldwide to frameworks like React and TensorFlow enabling ` +
      `rapid development, OSS accelerates innovation by allowing developers to build on ` +
      `shared foundations rather than reinventing the wheel.`;
  } else if (iterations === 2) {
    draft =
      `Open-source software (OSS) has fundamentally transformed modern technology, serving ` +
      `as the foundation for both startups and enterprise systems. Linux powers over 96% of ` +
      `the world's top servers, while frameworks like React, Kubernetes, and TensorFlow ` +
      `enable rapid development cycles. By enabling collaborative development across ` +
      `organizational boundaries, OSS accelerates innovation, reduces costs, and fosters ` +
      `a culture of transparency and shared knowledge.`;
  } else {
    draft =
      `Open-source software (OSS) has fundamentally transformed the technology landscape, ` +
      `serving as the bedrock for innovation from startups to Fortune 500 enterprises. ` +
      `Linux powers over 96% of the world's top servers, Kubernetes orchestrates ` +
      `containerized workloads at planetary scale, and machine learning frameworks like ` +
      `TensorFlow and PyTorch have democratized AI research. The OSS model accelerates ` +
      `innovation by enabling collaborative development across organizational boundaries, ` +
      `significantly reducing costs while fostering transparency, security through public ` +
      `scrutiny, and a vibrant culture of shared knowledge.`;
  }

  return { draft, iterations };
}

function reflect(state: ReflectionState): Partial<ReflectionState> {
  if (state.iterations >= MAX_ITERATIONS) {
    return { critique: 'APPROVE: The paragraph is well-structured, accurate, and engaging.' };
  }
  if (state.iterations === 1) {
    return {
      critique:
        'REVISE: The paragraph is a good start but lacks specific statistics and could be more ' +
        'engaging. Add concrete numbers and mention security benefits of open-source.',
    };
  }
  return {
    critique:
      'REVISE: Improved, but could benefit from mentioning the scale impact (e.g., Kubernetes) ' +
      'and the democratization of AI through open-source frameworks.',
  };
}

function shouldContinue(state: ReflectionState): string {
  if ((state.iterations ?? 0) >= MAX_ITERATIONS) return 'done';
  if (state.critique?.toUpperCase().startsWith('APPROVE')) return 'done';
  return 'improve';
}

function finalize(state: ReflectionState): Partial<ReflectionState> {
  return { finalOutput: state.draft };
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'reflection_agent',

  invoke: async (input: Record<string, unknown>) => {
    const topic = (input.input as string) ?? '';
    let state: ReflectionState = {
      topic,
      draft: '',
      critique: '',
      iterations: 0,
      finalOutput: '',
    };

    for (let i = 0; i < MAX_ITERATIONS + 1; i++) {
      state = { ...state, ...generate(state) };
      state = { ...state, ...reflect(state) };
      if (shouldContinue(state) === 'done') break;
    }

    state = { ...state, ...finalize(state) };
    return { output: state.finalOutput };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['generate', {}],
      ['reflect', {}],
      ['finalize', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'generate'],
      ['generate', 'reflect'],
      // Conditional: reflect -> generate | finalize
      ['finalize', '__end__'],
    ],
  }),

  nodes: new Map([
    ['generate', {}],
    ['reflect', {}],
    ['finalize', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const topic = (input.input as string) ?? '';
    let state: ReflectionState = {
      topic,
      draft: '',
      critique: '',
      iterations: 0,
      finalOutput: '',
    };

    for (let i = 0; i < MAX_ITERATIONS + 1; i++) {
      state = { ...state, ...generate(state) };
      yield ['updates', { generate: { draft: state.draft, iterations: state.iterations } }];

      state = { ...state, ...reflect(state) };
      yield ['updates', { reflect: { critique: state.critique } }];

      if (shouldContinue(state) === 'done') break;
    }

    state = { ...state, ...finalize(state) };
    yield ['updates', { finalize: { finalOutput: state.finalOutput } }];
    yield ['values', { output: state.finalOutput }];
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
      'the importance of open-source software in modern technology',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
