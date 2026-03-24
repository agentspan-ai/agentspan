/**
 * Vercel AI SDK — Passthrough
 *
 * Demonstrates passing a Vercel AI SDK ToolLoopAgent-like object
 * directly to runtime.run(). The SDK auto-detects the framework
 * and uses the passthrough worker pattern.
 */

import { AgentRuntime } from '../../src/index.js';

// -- Mock a Vercel AI SDK ToolLoopAgent-like object --
// Detection requires: .generate() + .stream() + .tools
// In production, this would be a real Vercel AI SDK agent
const vercelAgent = {
  // .generate() is called by the passthrough worker
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    return {
      text: `Vercel AI response to: ${options.prompt}`,
      toolCalls: [],
      finishReason: 'stop',
    };
  },
  // Required for framework detection
  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  // Name for identification
  id: 'vercel_research_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  // The runtime auto-detects Vercel AI SDK format and wraps it
  // in a passthrough worker. The framework agent runs locally,
  // but lifecycle is managed by the Agentspan server.
  console.log('Running Vercel AI agent via Agentspan...');
  const result = await runtime.run(vercelAgent, 'What is quantum computing?');
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
