/**
 * Structured Output — Zod output types.
 *
 * Demonstrates how to get typed, validated responses from an agent
 * using Zod schemas (the TypeScript equivalent of Pydantic models).
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

const WeatherReport = {
  type: 'object',
  properties: {
    city: { type: 'string' },
    temperature: { type: 'number' },
    condition: { type: 'string' },
    recommendation: { type: 'string' },
  },
  required: ['city', 'temperature', 'condition', 'recommendation'],
};

const getWeather = tool(
  async (args: { city: string }) => {
    return { city: args.city, temp_f: 72, condition: 'Sunny', humidity: 45 };
  },
  {
    name: 'get_weather',
    description: 'Get current weather data for a city.',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'The city to get weather for' },
      },
      required: ['city'],
    },
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

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, "What's the weather in NYC?");
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents weather_reporter
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
