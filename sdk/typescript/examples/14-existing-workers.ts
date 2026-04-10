/**
 * 14 - Existing Workers — reuse worker_task functions as agent tools.
 *
 * Demonstrates:
 *   - Using tool functions that mirror existing Conductor worker tasks
 *   - Mixing worker-backed and agent-specific tools in a single agent
 *   - The external: true option for referencing remote workers (shown but
 *     commented out since no remote workers are running in this demo)
 *
 * In the Python SDK, @worker_task decorated functions can be passed
 * directly as agent tools. In TypeScript, use tool() to wrap functions
 * that implement the same logic as your existing Conductor workers.
 * For truly remote workers, use { external: true } to reference task
 * definitions without registering a local handler.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// --- Existing worker task implementations ---
// These mirror @worker_task functions from an existing Conductor deployment.
// The function bodies match what your deployed workers do, so the agent
// gets the same behavior whether running locally or dispatched remotely.

const getCustomerData = tool(
  async (args: { customerId: string }) => {
    // In production this would query a real database
    const customers: Record<string, { name: string; plan: string; since: string }> = {
      C001: { name: 'Alice', plan: 'Enterprise', since: '2021-03' },
      C002: { name: 'Bob', plan: 'Starter', since: '2023-11' },
    };
    return customers[args.customerId] ?? { error: 'Customer not found' };
  },
  {
    name: 'get_customer_data',
    description: 'Fetch customer data from the database.',
    inputSchema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', description: 'The customer ID to look up' },
      },
      required: ['customerId'],
    },
  },
);

const getOrderHistory = tool(
  async (args: { customerId: string; limit?: number }) => {
    const orders: Record<string, { id: string; amount: number; status: string }[]> = {
      C001: [
        { id: 'ORD-101', amount: 250.0, status: 'delivered' },
        { id: 'ORD-098', amount: 89.99, status: 'delivered' },
      ],
      C002: [
        { id: 'ORD-110', amount: 45.0, status: 'shipped' },
      ],
    };
    const limit = args.limit ?? 5;
    return {
      customer_id: args.customerId,
      orders: (orders[args.customerId] ?? []).slice(0, limit),
    };
  },
  {
    name: 'get_order_history',
    description: 'Retrieve recent order history for a customer.',
    inputSchema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', description: 'The customer ID' },
        limit: { type: 'number', description: 'Max number of orders to return' },
      },
      required: ['customerId'],
    },
  },
);

// --- A new tool specific to this agent ---

const createSupportTicket = tool(
  async (args: { customerId: string; issue: string; priority?: string }) => {
    return {
      ticket_id: 'TKT-999',
      customer_id: args.customerId,
      issue: args.issue,
      priority: args.priority ?? 'medium',
    };
  },
  {
    name: 'create_support_ticket',
    description: 'Create a support ticket for a customer.',
    inputSchema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', description: 'The customer ID' },
        issue: { type: 'string', description: 'Description of the issue' },
        priority: { type: 'string', description: 'Ticket priority' },
      },
      required: ['customerId', 'issue'],
    },
  },
);

// --- For truly remote workers (no local handler), use external: true ---
// Uncomment below to reference an already-deployed Conductor task:
//
// const remoteTask = tool(
//   async (_args: { input: string }) => ({}), // body never called
//   {
//     name: 'my_deployed_task',
//     description: 'A task handled by an external Conductor worker.',
//     inputSchema: {
//       type: 'object',
//       properties: {
//         input: { type: 'string' },
//       },
//       required: ['input'],
//     },
//     external: true,  // No local worker — dispatched to remote handler
//   },
// );

// --- Agent that mixes worker-backed and agent-specific tools ---

export const agent = new Agent({
  name: 'customer_support',
  model: llmModel,
  tools: [getCustomerData, getOrderHistory, createSupportTicket],
  instructions:
    'You are a customer support agent. Use the available tools to look up ' +
    'customer information, check order history, and create support tickets.',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Customer C001 is asking about their recent orders. Look them up and summarize.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents customer_support
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
