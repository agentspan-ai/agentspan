/**
 * 51 - Shared State — tools sharing state across calls via ToolContext.
 *
 * Tools can read and write to `context.state`, a dictionary that persists
 * across all tool calls within the same agent execution.
 *
 * Requirements:
 *   - Conductor server with state support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import type { ToolContext } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tools -------------------------------------------------------------------

const addItem = tool(
  async (args: { item: string }, context?: ToolContext) => {
    const items: string[] = context?.state?.shopping_list ?? [];
    items.push(args.item);
    if (context?.state) {
      context.state.shopping_list = items;
    }
    return { added: args.item, total_items: items.length };
  },
  {
    name: 'add_item',
    description: 'Add an item to the shared shopping list.',
    inputSchema: z.object({
      item: z.string().describe('The item to add'),
    }),
  },
);

const getList = tool(
  async (_args: Record<string, never>, context?: ToolContext) => {
    const items: string[] = context?.state?.shopping_list ?? [];
    return { items, total_items: items.length };
  },
  {
    name: 'get_list',
    description: 'Get the current shopping list from shared state.',
    inputSchema: z.object({}),
  },
);

const clearList = tool(
  async (_args: Record<string, never>, context?: ToolContext) => {
    if (context?.state) {
      context.state.shopping_list = [];
    }
    return { status: 'cleared' };
  },
  {
    name: 'clear_list',
    description: 'Clear the shopping list.',
    inputSchema: z.object({}),
  },
);

// -- Agent -------------------------------------------------------------------

export const agent = new Agent({
  name: 'shopping_assistant_51',
  model: llmModel,
  instructions:
    'You help manage a shopping list. Use add_item to add items, ' +
    'get_list to view the list, and clear_list to reset it. ' +
    'IMPORTANT: Always add all items first, then call get_list separately ' +
    'in a follow-up step to verify the list contents. Never call get_list ' +
    'in the same batch as add_item calls.',
  tools: [addItem, getList, clearList],
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Add milk, eggs, and bread to my shopping list, then show me the list.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents shopping_assistant_51
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('51-shared-state.ts') || process.argv[1]?.endsWith('51-shared-state.js')) {
  main().catch(console.error);
}
