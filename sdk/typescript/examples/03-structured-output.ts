/**
 * Structured Output — Zod output types.
 *
 * Demonstrates how to get typed, validated responses from an agent
 * using Zod schemas (the TypeScript equivalent of Pydantic models).
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

const WeatherReport = z.object({
  city: z.string(),
  temperature: z.number(),
  condition: z.string(),
  recommendation: z.string(),
});

const getWeather = tool(
  async (args: { city: string }) => {
    return { city: args.city, temp_f: 72, condition: 'Sunny', humidity: 45 };
  },
  {
    name: 'get_weather',
    description: 'Get current weather data for a city.',
    inputSchema: z.object({
      city: z.string().describe('The city to get weather for'),
    }),
  },
);

export const agent = new Agent({
  name: 'weather_reporter',
  model: llmModel,
  tools: [getWeather],
  outputType: WeatherReport,
  instructions:
    'You are a weather reporter. Get the weather and provide a recommendation.',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(agent, "What's the weather in NYC?");
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('03-structured-output.ts') || process.argv[1]?.endsWith('03-structured-output.js')) {
  main().catch(console.error);
}
