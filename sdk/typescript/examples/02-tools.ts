/**
 * 02 - Tools
 *
 * Demonstrates multiple tool types:
 * - Native tool with Zod schema
 * - JSON Schema tool
 * - httpTool for external APIs
 *
 * Shows superset compatibility — all tool formats work together.
 */

import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  tool,
  httpTool,
  getToolDef,
} from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Native tool with Zod schema --
const calculator = tool(
  async (args: { expression: string }) => {
    // In production, use a proper math parser
    return { result: `Evaluated: ${args.expression}` };
  },
  {
    name: 'calculator',
    description: 'Evaluate a mathematical expression.',
    inputSchema: z.object({
      expression: z.string().describe('The math expression to evaluate'),
    }),
  },
);

// -- JSON Schema tool --
const weatherTool = tool(
  async (args: { city: string }) => {
    return { city: args.city, temperature: 22, unit: 'celsius' };
  },
  {
    name: 'get_weather',
    description: 'Get current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'City name' },
      },
      required: ['city'],
    },
  },
);

// -- HTTP tool (server-side execution) --
const searchApi = httpTool({
  name: 'web_search',
  description: 'Search the web for information.',
  url: 'https://api.example.com/search',
  method: 'GET',
  headers: { 'Authorization': 'Bearer ${SEARCH_API_KEY}' },
  inputSchema: {
    type: 'object',
    properties: {
      q: { type: 'string', description: 'Search query' },
    },
    required: ['q'],
  },
  credentials: ['SEARCH_API_KEY'],
});

// -- Create agent with all tools --
const agent = new Agent({
  name: 'research_assistant',
  model: MODEL,
  instructions: 'Use tools to answer questions accurately.',
  tools: [calculator, weatherTool, searchApi],
});

// -- Verify tool definitions --
console.log('Calculator tool def:', getToolDef(calculator).name);
console.log('Weather tool def:', getToolDef(weatherTool).name);
console.log('Search tool type:', searchApi.toolType);

// -- Run --
async function main() {
  const runtime = new AgentRuntime();
  const result = await runtime.run(agent, 'What is the weather in Paris?');
  result.printResult();
  await runtime.shutdown();
}

main().catch(console.error);
