/**
 * Vercel AI SDK — Tool Compatibility
 *
 * Demonstrates mixing agentspan tool() and Vercel AI SDK tool()
 * in the same agent. The SDK normalizes both formats.
 */

import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  tool,
  getToolDef,
} from '../../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Agentspan native tool --
const nativeTool = tool(
  async (args: { query: string }) => {
    return { results: [`Result for: ${args.query}`] };
  },
  {
    name: 'native_search',
    description: 'Search using agentspan native tool.',
    inputSchema: z.object({
      query: z.string().describe('Search query'),
    }),
  },
);

// -- Vercel AI SDK tool format --
// This mimics the Vercel AI SDK tool() shape:
// { parameters: ZodSchema, execute: Function, description: string }
const vercelTool = {
  description: 'Calculate a math expression using Vercel AI format.',
  parameters: z.object({
    expression: z.string().describe('Math expression'),
  }),
  execute: async (args: { expression: string }) => {
    return { result: `Calculated: ${args.expression}` };
  },
};

// -- Both tool formats normalize via getToolDef --
console.log('Native tool:', getToolDef(nativeTool).name);
console.log('Vercel tool:', getToolDef(vercelTool).name);

// -- Agent with mixed tools --
const agent = new Agent({
  name: 'mixed_tools_agent',
  model: MODEL,
  instructions: 'Use available tools to answer questions.',
  tools: [nativeTool, vercelTool],
});

async function main() {
  const runtime = new AgentRuntime();
  const result = await runtime.run(agent, 'Search for quantum computing and calculate 2+2.');
  result.printResult();
  await runtime.shutdown();
}

main().catch(console.error);
