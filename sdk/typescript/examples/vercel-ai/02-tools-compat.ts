/**
 * Vercel AI SDK Tools + Native Agent -- Tool Compatibility
 *
 * Demonstrates mixing Vercel AI SDK tool() with agentspan native tool()
 * in the same native Agent. The superset tool system normalizes both formats
 * to ToolDef automatically -- they work side by side without any conversion.
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  tool as agentspanTool,
  getToolDef,
} from '../../src/index.js';

// ── Agentspan native tool ────────────────────────────────
const nativeSearchTool = agentspanTool(
  async (args: { query: string }) => ({
    results: [`Result for: ${args.query}`],
  }),
  {
    name: 'native_search',
    description: 'Search using agentspan native tool format.',
    inputSchema: z.object({
      query: z.string().describe('Search query'),
    }),
  },
);

// ── Vercel AI SDK tool ───────────────────────────────────
const calculatorTool = aiTool({
  description: 'Evaluate a simple math expression.',
  parameters: z.object({
    expression: z.string().describe('Math expression to evaluate'),
  }),
  execute: async ({ expression }) => {
    try {
      const result = Function(`"use strict"; return (${expression})`)();
      return { expression, result: String(result) };
    } catch {
      return { expression, result: 'Error: could not evaluate' };
    }
  },
});

// ── Show normalized tool definitions ─────────────────────
console.log('Native tool def:', getToolDef(nativeSearchTool).name);
console.log('Vercel tool def:', getToolDef(calculatorTool).name);

// ── Native Agent mixing both tool formats ────────────────
const agent = new Agent({
  name: 'mixed_tools_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'You are a helpful assistant. Use the available tools to answer.',
  tools: [nativeSearchTool, calculatorTool], // Both formats coexist
});

const prompt = 'Search for quantum computing and also calculate 2 + 2.';

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
