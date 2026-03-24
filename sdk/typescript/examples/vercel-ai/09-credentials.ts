/**
 * Vercel AI SDK -- Credential Passthrough
 *
 * Demonstrates passing credentials (API keys) through Agentspan
 * to a Vercel AI SDK agent. The Vercel AI SDK uses the OPENAI_API_KEY
 * environment variable natively; Agentspan's credential system can
 * resolve and inject keys transparently.
 *
 * Path 1: Native generateText (uses env var directly).
 * Path 2: Agentspan passthrough (runtime resolves credentials).
 */

import { generateText } from 'ai';
import { openai } from '@ai-sdk/openai';
import { AgentRuntime } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');

const prompt = 'Summarize the latest research on transformer architectures in 2-3 sentences.';

// ── Check credentials ────────────────────────────────────
const hasOpenAIKey = !!process.env.OPENAI_API_KEY;
const hasAgentspanKey = !!process.env.AGENTSPAN_API_KEY;
console.log('Credential check:');
console.log('  OPENAI_API_KEY:', hasOpenAIKey ? 'set' : 'not set');
console.log('  AGENTSPAN_API_KEY:', hasAgentspanKey ? 'set' : 'not set');

if (!hasOpenAIKey) {
  console.log('\nSkipping execution -- OPENAI_API_KEY is required.');
  console.log('Set the environment variable and re-run:');
  console.log('  OPENAI_API_KEY=sk-... npx tsx examples/vercel-ai/09-credentials.ts');
  process.exit(0);
}

// ── Path 1: Native Vercel AI SDK ─────────────────────────
console.log('\n=== Native Vercel AI SDK ===');
const nativeResult = await generateText({
  model,
  prompt,
});
console.log('Output:', nativeResult.text);
console.log('Model:', nativeResult.response.modelId);
console.log('Usage:', nativeResult.usage);

// ── Path 2: Agentspan passthrough ────────────────────────
// In production, agentspan resolves the API key from its credential
// store and injects it into the environment before the agent runs.
// Here we demonstrate the wrapper pattern.
const vercelAgent = {
  id: 'credentialed_agent',
  tools: {},
  generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
    // The Vercel AI SDK reads OPENAI_API_KEY from the environment.
    // In production, agentspan would have already injected it.
    const result = await generateText({
      model,
      prompt: opts.prompt,
    });
    return {
      text: result.text,
      toolCalls: [],
      toolResults: [],
      finishReason: result.finishReason,
    };
  },
  stream: async function* () { yield { type: 'finish' as const }; },
};

console.log('\n=== Agentspan Passthrough ===');
const runtime = new AgentRuntime();
try {
  const agentspanResult = await runtime.run(vercelAgent, prompt);
  console.log('Output:', JSON.stringify(agentspanResult.output));
  console.log('Status:', agentspanResult.status);
} finally {
  await runtime.shutdown();
}
