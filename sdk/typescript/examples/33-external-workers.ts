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

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

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
    inputSchema: {
      type: 'object',
      properties: {
        orderId: { type: 'string', description: 'The order ID' },
        action: { type: 'string', description: 'Action to take: refund, cancel, or update' },
      },
      required: ['orderId', 'action'],
    },
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
    inputSchema: {
      type: 'object',
      properties: {
        userId: { type: 'string', description: 'The user ID to delete' },
        reason: { type: 'string', description: 'Reason for deletion' },
      },
      required: ['userId', 'reason'],
    },
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
    inputSchema: {
      type: 'object',
      properties: {
        data: { type: 'object', additionalProperties: true, description: 'Data to format' },
      },
      required: ['data'],
    },
  },
);

const getCustomer = tool(
  async (_args: { customerId: string }) => {
    return {};
  },
  {
    name: 'get_customer',
    description: 'Look up customer details from the CRM system.',
    inputSchema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', description: 'The customer ID' },
      },
      required: ['customerId'],
    },
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
    inputSchema: {
      type: 'object',
      properties: {
        productId: { type: 'string', description: 'The product ID' },
        warehouse: { type: 'string', description: 'Warehouse name' },
      },
      required: ['productId'],
    },
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

async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('=== External Worker Tools ===');
    console.log('Agent has 1 local tool + 3 external worker references.\n');

    const result = await runtime.run(
    supportAgent,
    'Customer C-1234 wants to cancel order ORD-5678. ' +
    'Look up the customer, check if we have the product in stock, ' +
    'and process the cancellation.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(supportAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents support_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(supportAgent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
