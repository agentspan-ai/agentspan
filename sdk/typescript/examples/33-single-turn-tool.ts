/**
 * 33 - Single-Turn Tool Call
 *
 * The simplest tool-calling pattern: the user asks a question, the LLM
 * calls a tool to get data, then responds with the answer. No iterative
 * loop -- the agent runs for exactly one exchange.
 *
 * Compiled workflow:
 *   LLM(prompt, tools) -> tool executes -> LLM sees result -> answer
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
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
      city: z.string().describe('City name'),
    }),
  },
);

export const agent = new Agent({
  name: 'weather_agent',
  model: llmModel,
  instructions: 'You are a weather assistant. Use the get_weather tool to answer.',
  tools: [getWeather],
  maxTurns: 2, // 1 turn to call the tool, 1 turn to answer
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
    // const result = await runtime.run(agent, "What's the weather in San Francisco?");
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('33-single-turn-tool.ts') || process.argv[1]?.endsWith('33-single-turn-tool.js')) {
  main().catch(console.error);
}
