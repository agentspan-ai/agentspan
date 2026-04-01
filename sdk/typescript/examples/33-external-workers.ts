/**
 * 33 - External Worker Tools
 *
 * Demonstrates tool({ external: true }) for referencing Conductor workers that
 * exist in another repository, service, or language. The function stub provides
 * the schema (via Zod) and description, but no local worker is started --
 * Conductor dispatches the task to whatever worker is polling for that task
 * definition name.
 *
 * This is useful when:
 *   - Workers are written in Java, Go, or another language
 *   - Workers run in a separate microservice
 *   - You want to reuse existing Conductor task definitions
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - The referenced workers must be running somewhere
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Basic external worker reference ------------------------------
// The function stub defines the schema; no implementation needed.
// Conductor dispatches "process_order" tasks to whatever worker is polling.

const processOrder = tool(
  async (_args: { orderId: string; action: string }) => {
    // This function body is never called for external tools.
    return {};
  },
  {
    name: 'process_order',
    description: 'Process a customer order. Actions: refund, cancel, update.',
    inputSchema: z.object({
      orderId: z.string().describe('The order ID'),
      action: z.string().describe('Action to take: refund, cancel, or update'),
    }),
    external: true,
  },
);

// -- Example 2: External worker with approval gate ---------------------------
// Dangerous operations can require human approval before execution.

const deleteAccount = tool(
  async (_args: { userId: string; reason: string }) => {
    return {};
  },
  {
    name: 'delete_account',
    description: 'Permanently delete a user account. Requires manager approval.',
    inputSchema: z.object({
      userId: z.string().describe('The user ID to delete'),
      reason: z.string().describe('Reason for deletion'),
    }),
    external: true,
    approvalRequired: true,
  },
);

// -- Example 3: Mix local and external tools ---------------------------------

const formatResponse = tool(
  async (args: { data: Record<string, unknown> }) => {
    return Object.entries(args.data)
      .map(([k, v]) => `  ${k}: ${v}`)
      .join('\n');
  },
  {
    name: 'format_response',
    description: 'Format a data dictionary into a human-readable string.',
    inputSchema: z.object({
      data: z.record(z.unknown()).describe('Data to format'),
    }),
  },
);

const getCustomer = tool(
  async (_args: { customerId: string }) => {
    return {};
  },
  {
    name: 'get_customer',
    description: 'Look up customer details from the CRM system.',
    inputSchema: z.object({
      customerId: z.string().describe('The customer ID'),
    }),
    external: true,
  },
);

const checkInventory = tool(
  async (_args: { productId: string; warehouse?: string }) => {
    return {};
  },
  {
    name: 'check_inventory',
    description: 'Check product availability in a warehouse.',
    inputSchema: z.object({
      productId: z.string().describe('The product ID'),
      warehouse: z.string().optional().default('default').describe('Warehouse name'),
    }),
    external: true,
  },
);

// -- Agent: combines local + external tools ----------------------------------

export const supportAgent = new Agent({
  name: 'support_agent',
  model: llmModel,
  instructions:
    'You are a customer support agent. Use the available tools to ' +
    'look up customers, check inventory, process orders, and format ' +
    'responses for the customer.',
  tools: [
    formatResponse,   // Local -- runs in this process
    getCustomer,      // External -- runs in CRM service
    checkInventory,   // External -- runs in inventory service
    processOrder,     // External -- runs in order service
  ],
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(supportAgent);
    // await runtime.serve(supportAgent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    console.log('=== External Worker Tools ===');
    console.log('Agent has 1 local tool + 3 external worker references.\n');

    const result = await runtime.run(
    supportAgent,
    'Customer C-1234 wants to cancel order ORD-5678. ' +
    'Look up the customer, check if we have the product in stock, ' +
    'and process the cancellation.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('33-external-workers.ts') || process.argv[1]?.endsWith('33-external-workers.js')) {
  main().catch(console.error);
}
