/**
 * Vercel AI SDK Tools + Native Agent -- Streaming
 *
 * Demonstrates streaming events from a native agentspan Agent using AI SDK tools.
 * Uses runtime.stream() which returns an AgentStream (AsyncIterable<AgentEvent>).
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
const agent = new Agent({
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
    const agentStream = await runtime.stream(agent, prompt);

    console.log('Streaming events:');
    for await (const event of agentStream) {
      console.log(`  [${event.type}]`, event.content ?? event.toolName ?? '');
    }

    const result = await agentStream.getResult();
    console.log('\nStatus:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
