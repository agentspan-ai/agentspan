/**
 * Streaming Tokens -- streaming intermediate LLM output token by token.
 *
 * Demonstrates:
 *   - Using graph.stream() with stream_mode="messages" to receive tokens
 *   - Printing partial output as it arrives for a real-time feel
 *   - How LangGraph exposes AIMessageChunk events during generation
 *   - Practical use case: streaming a long-form answer to the terminal
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   for await (const [eventType, chunk] of graph.stream(input, { streamMode: "messages" })) { ... }
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Mock response content
// ---------------------------------------------------------------------------
const GRADIENT_DESCENT_EXPLANATION =
  `Gradient descent is a fundamental optimization algorithm used extensively in machine learning ` +
  `to minimize a loss function. The algorithm works by iteratively adjusting model parameters ` +
  `in the direction of steepest descent of the loss surface. At each step, the gradient ` +
  `(partial derivatives) of the loss function with respect to each parameter is computed, ` +
  `indicating the direction of maximum increase. The parameters are then updated by moving ` +
  `in the opposite direction, scaled by a learning rate hyperparameter. Variants include ` +
  `stochastic gradient descent (SGD), which uses random mini-batches for efficiency, ` +
  `and adaptive methods like Adam and RMSprop that adjust learning rates per parameter. ` +
  `The choice of learning rate is critical: too large causes divergence, too small leads ` +
  `to slow convergence. Modern deep learning relies heavily on gradient descent and its ` +
  `variants to train neural networks with millions or billions of parameters.`;

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'streaming_agent',

  invoke: async (input: Record<string, unknown>) => {
    return {
      messages: [
        { role: 'assistant', content: GRADIENT_DESCENT_EXPLANATION },
      ],
    };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['generate', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'generate'],
      ['generate', '__end__'],
    ],
  }),

  nodes: new Map([['generate', {}]]),

  stream: async function* (input: Record<string, unknown>) {
    // Simulate token-by-token streaming
    const words = GRADIENT_DESCENT_EXPLANATION.split(' ');
    for (let i = 0; i < words.length; i++) {
      const token = (i > 0 ? ' ' : '') + words[i];
      yield ['messages', { type: 'AIMessageChunk', content: token }];
    }
    yield [
      'values',
      {
        messages: [
          { role: 'assistant', content: GRADIENT_DESCENT_EXPLANATION },
        ],
      },
    ];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('Running streaming agent via Agentspan...\n');
    const result = await runtime.run(
      graph,
      'Explain the concept of gradient descent in machine learning in about 150 words.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
