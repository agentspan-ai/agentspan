/**
 * Google ADK Shared State -- tools sharing state via tool_context.
 *
 * Tools can read and write shared state, a dictionary that persists
 * across tool calls within the same agent execution.
 *
 * Demonstrates:
 *   - Tools using the tool_context (Context) parameter to access shared state
 *   - State persistence across multiple tool calls
 *   - Simple shopping list CRUD via shared state
 *
 * Note: In the TypeScript ADK, tool functions receive an optional `tool_context`
 * (Context) parameter that provides access to session state.
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── In-memory state (simulating ADK ToolContext shared state) ────────
// In the real ADK, this would be context.state. For the agentspan
// passthrough, we simulate with module-level state.

const sharedState: { shopping_list: string[] } = { shopping_list: [] };

// ── Tool definitions ─────────────────────────────────────────────────

const addItem = new FunctionTool({
  name: 'add_item',
  description: 'Add an item to the shared shopping list.',
  parameters: z.object({
    item: z.string().describe('The item to add'),
  }),
  execute: async (args: { item: string }) => {
    sharedState.shopping_list.push(args.item);
    return { added: args.item, total_items: sharedState.shopping_list.length };
  },
});

const getList = new FunctionTool({
  name: 'get_list',
  description: 'Get the current shopping list from shared state.',
  parameters: z.object({}),
  execute: async () => {
    return { items: [...sharedState.shopping_list], total_items: sharedState.shopping_list.length };
  },
});

const clearList = new FunctionTool({
  name: 'clear_list',
  description: 'Clear the shopping list.',
  parameters: z.object({}),
  execute: async () => {
    sharedState.shopping_list = [];
    return { status: 'cleared' };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'shopping_assistant',
  model,
  instruction:
    'You help manage a shopping list. Use add_item to add items, ' +
    'get_list to view the list, and clear_list to reset it.',
  tools: [addItem, getList, clearList],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    const result = await runtime.run(
    agent,
    'Add milk, eggs, and bread to my shopping list, then show me the list.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('31-shared-state.ts') || process.argv[1]?.endsWith('31-shared-state.js')) {
  main().catch(console.error);
}
