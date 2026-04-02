// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent Handoffs -- multi-agent orchestration with handoffs.
 *
 * Demonstrates:
 *   - Defining specialist agents with tools
 *   - A triage agent that routes to the correct specialist via handoffs
 *   - Running via Agentspan passthrough
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, tool, setTracingDisabled } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Specialist tools ────────────────────────────────────────────────

const checkOrderStatus = tool({
  name: 'check_order_status',
  description: 'Check the status of a customer order.',
  parameters: z.object({ order_id: z.string().describe('The order ID') }),
  execute: async ({ order_id }) => {
    const orders: Record<string, string> = {
      'ORD-001': 'Shipped -- arriving tomorrow',
      'ORD-002': 'Processing -- estimated ship date: Friday',
      'ORD-003': 'Delivered on Monday',
    };
    return orders[order_id] ?? `Order ${order_id} not found`;
  },
});

const processRefund = tool({
  name: 'process_refund',
  description: 'Process a refund for an order.',
  parameters: z.object({
    order_id: z.string().describe('The order ID'),
    reason: z.string().describe('Reason for refund'),
  }),
  execute: async ({ order_id, reason }) => {
    return `Refund initiated for ${order_id}. Reason: ${reason}. Expect 3-5 business days.`;
  },
});

const getProductInfo = tool({
  name: 'get_product_info',
  description: 'Get product information and pricing.',
  parameters: z.object({ product_name: z.string().describe('Product name') }),
  execute: async ({ product_name }) => {
    const products: Record<string, string> = {
      'laptop pro': 'Laptop Pro X1 -- $1,299 -- 16GB RAM, 512GB SSD, 14" display',
      'wireless earbuds': 'SoundMax Earbuds -- $79 -- ANC, 24hr battery, Bluetooth 5.3',
      'smart watch': 'TimeSync Watch -- $249 -- GPS, health tracking, 5-day battery',
    };
    return products[product_name.toLowerCase()] ?? `Product '${product_name}' not found`;
  },
});

// ── Specialist agents ───────────────────────────────────────────────

export const orderAgent = new Agent({
  name: 'order_specialist',
  instructions:
    'You handle order-related inquiries. Use the check_order_status tool ' +
    'to look up orders. Be professional and concise.',
  model: 'gpt-4o-mini',
  tools: [checkOrderStatus],
});

export const refundAgent = new Agent({
  name: 'refund_specialist',
  instructions:
    'You handle refund requests. Use the process_refund tool to initiate ' +
    'refunds. Always confirm the order ID and reason before processing.',
  model: 'gpt-4o-mini',
  tools: [processRefund],
});

export const salesAgent = new Agent({
  name: 'sales_specialist',
  instructions:
    'You handle product inquiries and sales. Use the get_product_info tool ' +
    'to look up products. Be enthusiastic but not pushy.',
  model: 'gpt-4o-mini',
  tools: [getProductInfo],
});

// ── Triage agent with handoffs ──────────────────────────────────────

export const triageAgent = new Agent({
  name: 'customer_service_triage',
  instructions:
    'You are a customer service triage agent. Determine the customer\'s need ' +
    'and hand off to the appropriate specialist:\n' +
    '- Order status inquiries -> order_specialist\n' +
    '- Refund requests -> refund_specialist\n' +
    '- Product questions or purchases -> sales_specialist\n' +
    'Be brief in your initial response before handing off.',
  model: 'gpt-4o-mini',
  handoffs: [orderAgent, refundAgent, salesAgent],
});

const prompt = "I'd like a refund for order ORD-002, the product arrived damaged.";

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(triageAgent, prompt);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(triageAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/openai --agents customer_service_triage
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(triageAgent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('04-handoffs.ts') || process.argv[1]?.endsWith('04-handoffs.js')) {
  main().catch(console.error);
}
