/**
 * Vercel AI SDK -- Credential Passthrough
 *
 * Demonstrates passing credentials (API keys, tokens) through Agentspan
 * to a Vercel AI SDK agent. The runtime handles credential resolution
 * and injection transparently.
 *
 * In production you would use:
 *   import { generateText } from 'ai';
 *   import { openai } from '@ai-sdk/openai';
 *   // API key resolved by Agentspan credential system
 */

import { AgentRuntime } from '../../src/index.js';

// -- Mock Vercel AI SDK agent that requires credentials --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    // In production, the Agentspan runtime injects the resolved API key
    // into the provider configuration automatically.
    const hasCredential = !!(
      process.env.OPENAI_API_KEY ||
      process.env.AGENTSPAN_API_KEY
    );

    return {
      text: hasCredential
        ? `[Credential: resolved] Response to: "${options.prompt.slice(0, 50)}..."\n\n` +
          'The Agentspan credential system resolved the required API key and ' +
          'injected it into the provider configuration. No manual key management needed.'
        : '[Credential: missing] Unable to process -- no API key available. ' +
          'Configure credentials via Agentspan dashboard or environment variables.',
      toolCalls: [],
      finishReason: 'stop' as const,
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  id: 'vercel_credentialed_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  console.log('Running Vercel AI agent with credential passthrough...\n');
  const result = await runtime.run(
    vercelAgent,
    'Summarize the latest research on transformer architectures.',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
