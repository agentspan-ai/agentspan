/**
 * Vercel AI SDK Tools + Native Agent -- Streaming
 *
 * Demonstrates the default runtime.run() happy path with AI SDK tools.
 * Includes a commented runtime.stream() alternative for event streaming.
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import { Agent, AgentRuntime } from '../../src/index.js';

// ── Vercel AI SDK tool ───────────────────────────────────
const weatherTool = aiTool({
  description: 'Get current weather for a city',
  parameters: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city,
    tempF: 62,
    condition: 'Foggy',
  }),
});

// ── Native Agent ─────────────────────────────────────────
export const agent = new Agent({
  name: 'streaming_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'You are a helpful assistant. Use tools when relevant.',
  tools: [weatherTool],
});

const prompt = 'Explain quantum computing in one paragraph, then tell me the weather in San Francisco.';

// ── Stream on agentspan ──────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/vercel-ai --agents streaming_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
    //
    // Streaming alternative:
    // const agentStream = await runtime.stream(agent, prompt);
    // for await (const event of agentStream) {
    //   console.log(`  [${event.type}]`, event.content ?? event.toolName ?? '');
    // }
    // const streamedResult = await agentStream.getResult();
    // streamedResult.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('03-streaming.ts') || process.argv[1]?.endsWith('03-streaming.js')) {
  main().catch(console.error);
}
