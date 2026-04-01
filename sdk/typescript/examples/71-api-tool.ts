/**
 * 71 - API Tool — auto-discover endpoints from OpenAPI, Swagger, or Postman specs.
 *
 * Demonstrates apiTool(), which points to an API spec and automatically
 * discovers all operations as agent tools. No manual tool definitions needed.
 *
 * Three patterns shown:
 *   1. OpenAPI 3.x spec URL
 *   2. Base URL (server auto-discovers /openapi.json, etc.)
 *   3. Mixing apiTool with other tool types
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, apiTool, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: OpenAPI spec -------------------------------------------------

const petstore = apiTool({
  url: 'https://petstore3.swagger.io/api/v3/openapi.json',
  name: 'petstore',
  maxTools: 20,
});

export const petAgent = new Agent({
  name: 'pet_store_assistant',
  model: llmModel,
  instructions: 'You help users manage a pet store. Use the available API tools.',
  tools: [petstore],
});

// -- Example 2: Base URL (auto-discovery) ------------------------------------

const weather = apiTool({
  url: 'https://api.weather.com',
  toolNames: ['getCurrentWeather', 'getForecast'],
});

export const weatherAgent = new Agent({
  name: 'weather_assistant',
  model: llmModel,
  instructions: 'You provide weather information.',
  tools: [weather],
});

// -- Example 3: Mix apiTool with other tool types ----------------------------

const calculate = tool(
  async (args: { expression: string }) => {
    const safeBuiltins: Record<string, (...a: number[]) => number> = {
      abs: Math.abs,
      round: Math.round,
      sqrt: Math.sqrt,
      pow: Math.pow,
    };
    try {
      const fn = new Function(...Object.keys(safeBuiltins), `return (${args.expression});`);
      return { expression: args.expression, result: fn(...Object.values(safeBuiltins)) };
    } catch (e) {
      return { expression: args.expression, error: String(e) };
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a math expression.',
    inputSchema: z.object({
      expression: z.string().describe('A mathematical expression'),
    }),
  },
);

const petstoreApi = apiTool({
  url: 'https://petstore3.swagger.io/api/v3/openapi.json',
  maxTools: 10,
});

export const multiToolAgent = new Agent({
  name: 'multi_tool_assistant',
  model: llmModel,
  instructions:
    'You are a versatile assistant. Use API tools for pet store operations, ' +
    'and the calculator for math. Pick the best tool for each request.',
  tools: [petstoreApi, calculate],
});

// -- Example 4: Large API with credential auth -------------------------------

const github = apiTool({
  url: 'https://api.github.com',
  headers: {
    Authorization: 'token ${GITHUB_TOKEN}',
    Accept: 'application/vnd.github+json',
  },
  credentials: ['GITHUB_TOKEN'],
  toolNames: [
    'repos_list_for_user',
    'repos_create_for_authenticated_user',
    'issues_list_for_repo',
    'issues_create',
  ],
  maxTools: 20,
});

export const githubAgent = new Agent({
  name: 'github_assistant',
  model: llmModel,
  instructions: 'You help users manage their GitHub repositories and issues.',
  tools: [github],
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(petAgent);
    // await runtime.serve(petAgent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    // Example 1: Petstore
    console.log('=== Petstore API ===');
    const result = await runtime.run(petAgent, "List all available pets with status 'available'");
    result.printResult();

    // Example 3: Mixed tools
    console.log('\n=== Mixed Tools ===');
    const result2 = await runtime.run(multiToolAgent, "What's sqrt(144)? Also find pets named 'doggie'.");
    result2.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('71-api-tool.ts') || process.argv[1]?.endsWith('71-api-tool.js')) {
  main().catch(console.error);
}
