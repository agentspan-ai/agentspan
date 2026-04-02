/**
 * Callbacks -- tool interception with beforeToolCallback / afterToolCallback.
 *
 * Demonstrates:
 *   - ADK callback API pattern (beforeToolCallback, afterToolCallback)
 *   - Tools for customer service: lookup, discount, order status
 *   - Callback functions that can validate inputs and modify outputs
 *
 * NOTE: ADK callbacks are client-side hooks that run within the ADK framework.
 * When compiled to server workflows, these callbacks are serialized but may not
 * execute server-side. This example demonstrates the ADK API pattern.
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const lookupCustomer = new FunctionTool({
  name: 'lookup_customer',
  description: 'Look up customer information by ID.',
  parameters: z.object({
    customer_id: z.string().describe('The customer ID to look up'),
  }),
  execute: async (args: { customer_id: string }) => {
    const customers: Record<string, { name: string; tier: string; balance: number }> = {
      C001: { name: 'Alice Smith', tier: 'gold', balance: 1500.0 },
      C002: { name: 'Bob Jones', tier: 'silver', balance: 320.5 },
      C003: { name: 'Carol White', tier: 'bronze', balance: 50.0 },
    };
    const customer = customers[args.customer_id.toUpperCase()];
    if (customer) {
      return { found: true, customer_id: args.customer_id, ...customer };
    }
    return { found: false, error: `Customer ${args.customer_id} not found` };
  },
});

const applyDiscount = new FunctionTool({
  name: 'apply_discount',
  description: 'Apply a discount to a customer\'s account.',
  parameters: z.object({
    customer_id: z.string().describe('The customer ID'),
    discount_percent: z.number().describe('Discount percentage to apply'),
  }),
  execute: async (args: { customer_id: string; discount_percent: number }) => {
    if (args.discount_percent > 50) {
      return { error: 'Discount cannot exceed 50%' };
    }
    return {
      status: 'success',
      customer_id: args.customer_id,
      discount_applied: `${args.discount_percent}%`,
      message: `Applied ${args.discount_percent}% discount to ${args.customer_id}`,
    };
  },
});

const checkOrderStatus = new FunctionTool({
  name: 'check_order_status',
  description: 'Check the status of an order.',
  parameters: z.object({
    order_id: z.string().describe('The order ID to check'),
  }),
  execute: async (args: { order_id: string }) => {
    const orders: Record<string, { status: string; tracking: string | null; eta: string }> = {
      'ORD-1001': { status: 'shipped', tracking: 'TRK-98765', eta: '2025-04-20' },
      'ORD-1002': { status: 'processing', tracking: null, eta: '2025-04-25' },
    };
    return orders[args.order_id.toUpperCase()] ?? { error: `Order ${args.order_id} not found` };
  },
});

// ── Agent with callbacks ────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'customer_service_agent',
  model,
  instruction:
    'You are a helpful customer service agent. ' +
    'Use the available tools to look up customer information, ' +
    'check order status, and apply discounts when requested. ' +
    'Always verify the customer exists before applying discounts.',
  tools: [lookupCustomer, applyDiscount, checkOrderStatus],

  // NOTE: Callbacks demonstrate the ADK API pattern.
  // beforeToolCallback can intercept/validate tool inputs.
  // afterToolCallback can modify tool outputs.
  beforeToolCallback: async ({ tool, args, context }) => {
    console.log(`  [beforeTool] ${tool.name} called with`, JSON.stringify(args));
    // Return undefined to proceed with normal tool execution
    return undefined;
  },
  afterToolCallback: async ({ tool, args, context, response }) => {
    console.log(`  [afterTool] ${tool.name} returned`, JSON.stringify(response).slice(0, 100));
    // Return undefined to use the original response
    return undefined;
  },
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Look up customer C001 and check if order ORD-1001 has shipped. ' +
    'If the customer is gold tier, apply a 10% discount.',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents customer_service_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('14-callbacks.ts') || process.argv[1]?.endsWith('14-callbacks.js')) {
  main().catch(console.error);
}
