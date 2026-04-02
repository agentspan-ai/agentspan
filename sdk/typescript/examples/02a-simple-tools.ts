/**
 * Simple Tool Calling — two tools, the LLM picks the right one.
 *
 * The agent has two tools: one for weather, one for stock prices.
 * Based on the user's question, the LLM decides which tool to call.
 *
 * In the Conductor UI you'll see each tool call as a separate task
 * (DynamicTask) with its inputs and outputs clearly visible.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

const getWeather = tool(
  async (args: { city: string }) => {
    return { city: args.city, temp_f: 72, condition: 'Sunny' };
  },
  {
    name: 'get_weather',
    description: 'Get the current weather for a city.',
    inputSchema: z.object({
      city: z.string().describe('The city to get weather for'),
    }),
  },
);

const getStockPrice = tool(
  async (args: { symbol: string }) => {
    return { symbol: args.symbol, price: 182.5, change: '+1.2%' };
  },
  {
    name: 'get_stock_price',
    description: 'Get the current stock price for a ticker symbol.',
    inputSchema: z.object({
      symbol: z.string().describe('The stock ticker symbol'),
    }),
  },
);

export const agent = new Agent({
  name: 'weather_stock_agent',
  model: llmModel,
  tools: [getWeather, getStockPrice],
  instructions: 'You are a helpful assistant. Use tools to answer questions.',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // The LLM will call get_weather (not get_stock_price)
    const result = await runtime.run(
    agent,
    "What's the weather like in San Francisco?",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents weather_stock_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('02a-simple-tools.ts') || process.argv[1]?.endsWith('02a-simple-tools.js')) {
  main().catch(console.error);
}
