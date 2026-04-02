/**
 * Vercel AI SDK Tools + Native Agent -- Basic Agent
 *
 * Demonstrates using Vercel AI SDK tool() objects with a native agentspan Agent.
 * The superset tool system auto-detects AI SDK tool format (Zod parameters + execute)
 * and converts them to agentspan ToolDefs transparently.
 *
 * No duck-typed wrappers or passthrough needed -- just native Agent with AI SDK tools.
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import { Agent, AgentRuntime } from '../../src/index.js';

// ── Vercel AI SDK tool (auto-detected by superset tool system) ──
const weatherTool = aiTool({
  description: 'Get current weather for a city',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => ({
    city,
    tempF: 62,
    condition: 'Foggy',
  }),
});

// ── Native agentspan Agent with AI SDK tool ─────────────
export const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'You are a helpful assistant. Use available tools to answer questions.',
  tools: [weatherTool], // AI SDK tool auto-converted by superset system
});

const prompt = 'What is the weather in San Francisco?';

// ── Run on agentspan ─────────────────────────────────────
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
    // agentspan deploy --package sdk/typescript/examples/vercel-ai --agents weather_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('01-basic-agent.ts') || process.argv[1]?.endsWith('01-basic-agent.js')) {
  main().catch(console.error);
}
