/**
 * Vercel AI SDK -- Streaming
 *
 * Demonstrates streaming Vercel AI SDK agent events through Agentspan.
 * The agent produces tokens incrementally and the runtime streams them
 * to the caller in real time.
 *
 * In production you would use:
 *   import { streamText } from 'ai';
 *   const result = await streamText({ model, prompt });
 *   for await (const chunk of result.textStream) { ... }
 */

import { AgentRuntime } from '../../src/index.js';

// -- Mock a Vercel AI SDK agent with streaming support --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    const tokens = [
      'Quantum ', 'computing ', 'harnesses ', 'quantum ', 'mechanical ',
      'phenomena ', 'like ', 'superposition ', 'and ', 'entanglement ',
      'to ', 'process ', 'information ', 'in ', 'fundamentally ', 'new ',
      'ways. ', 'Unlike ', 'classical ', 'bits, ', 'qubits ', 'can ',
      'exist ', 'in ', 'multiple ', 'states ', 'simultaneously, ',
      'enabling ', 'certain ', 'computations ', 'to ', 'be ', 'performed ',
      'exponentially ', 'faster.',
    ];
    return {
      text: tokens.join(''),
      toolCalls: [],
      finishReason: 'stop' as const,
    };
  },

  stream: async function* (options: { prompt: string }) {
    const tokens = [
      'Quantum ', 'computing ', 'harnesses ', 'quantum ', 'mechanical ',
      'phenomena ', 'like ', 'superposition ', 'and ', 'entanglement ',
      'to ', 'process ', 'information ', 'in ', 'fundamentally ', 'new ',
      'ways.',
    ];
    for (const token of tokens) {
      yield { type: 'text-delta' as const, textDelta: token };
    }
    yield { type: 'finish' as const, finishReason: 'stop' as const };
  },

  tools: [],
  id: 'vercel_streaming_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  console.log('Streaming Vercel AI agent via Agentspan...\n');
  const result = await runtime.run(
    vercelAgent,
    'Explain quantum computing in one paragraph.',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
