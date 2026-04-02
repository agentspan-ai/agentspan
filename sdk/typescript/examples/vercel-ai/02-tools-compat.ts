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
export const nativeSearchTool = agentspanTool(
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

// ── Native Agent mixing both tool formats ────────────────
export const agent = new Agent({
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

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/vercel-ai --agents mixed_tools_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('02-tools-compat.ts') || process.argv[1]?.endsWith('02-tools-compat.js')) {
  // Show normalized tool definitions
  console.log('Native tool def:', getToolDef(nativeSearchTool).name);
  console.log('Vercel tool def:', getToolDef(calculatorTool).name);

  main().catch(console.error);
}
