/**
 * Agent with tools — define a tool function, agent calls it.
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../../src/index.js';
import { llmModel } from '../settings.js';

const getWeather = tool(
  async (args: { city: string }) => {
    return { city: args.city, temp_f: 72, condition: 'Sunny' };
  },
  {
    name: 'get_weather',
    description: 'Get current weather for a city.',
    inputSchema: z.object({
      city: z.string().describe('The city to get weather for'),
    }),
  },
);

export const agent = new Agent({
  name: 'weather_bot',
  model: llmModel,
  instructions: 'Use the get_weather tool to answer weather questions.',
  tools: [getWeather],
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, "What's the weather in Tokyo?");
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

export const prompt = "What's the weather in Tokyo?";

if (process.argv[1]?.includes('02-tools')) {
  main().catch(console.error);
}
