/**
 * Vercel AI SDK Tools + Native Agent -- Multi-Step
 *
 * Demonstrates a native agentspan Agent with multiple AI SDK tools and maxTurns.
 * The agent calls tools iteratively until it has enough information to produce
 * a final answer. maxTurns controls the maximum number of LLM turns.
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import { Agent, AgentRuntime } from '../../src/index.js';

// ── Tool data ────────────────────────────────────────────
const weatherData: Record<string, string> = {
  'san francisco': '62F, Foggy',
  'new york': '45F, Cloudy',
  'tokyo': '58F, Clear',
  'london': '50F, Rainy',
};

const timeData: Record<string, string> = {
  'san francisco': '09:30 PST (UTC-8)',
  'new york': '12:30 EST (UTC-5)',
  'tokyo': '02:30 JST (UTC+9)',
  'london': '17:30 GMT (UTC+0)',
};

// ── Vercel AI SDK tools ──────────────────────────────────
const lookupWeather = aiTool({
  description: 'Look up current weather for a city.',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => {
    const data = weatherData[city.toLowerCase()];
    return data ?? `Weather data not available for ${city}`;
  },
});

const lookupTime = aiTool({
  description: 'Look up current local time for a city.',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => {
    const data = timeData[city.toLowerCase()];
    return data ?? `Time data not available for ${city}`;
  },
});

// ── Native Agent with multiple tools and maxTurns ────────
export const agent = new Agent({
  name: 'multistep_agent',
  model: 'openai/gpt-4o-mini',
  instructions:
    'You are a helpful assistant. Use the available tools to look up weather and time data, then summarize the results.',
  tools: [lookupWeather, lookupTime],
  maxTurns: 8, // Maximum number of LLM turns
});

const prompt = 'What is the current weather and time in San Francisco and Tokyo?';

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    console.log('Tool calls:', result.toolCalls.length);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/vercel-ai --agents multistep_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('05-multi-step.ts') || process.argv[1]?.endsWith('05-multi-step.js')) {
  main().catch(console.error);
}
