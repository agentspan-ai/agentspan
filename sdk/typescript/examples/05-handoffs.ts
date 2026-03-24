/**
 * Handoffs — agent delegating to sub-agents.
 *
 * Demonstrates the handoff strategy where the parent agent's LLM decides
 * which sub-agent to delegate to. Sub-agents appear as callable tools.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Sub-agent tools --------------------------------------------------------

const checkBalance = tool(
  async (args: { accountId: string }) => {
    return { account_id: args.accountId, balance: 5432.10, currency: 'USD' };
  },
  {
    name: 'check_balance',
    description: 'Check the balance of a bank account.',
    inputSchema: z.object({
      accountId: z.string().describe('The account ID to check'),
    }),
  },
);

const lookupOrder = tool(
  async (args: { orderId: string }) => {
    return { order_id: args.orderId, status: 'shipped', eta: '2 days' };
  },
  {
    name: 'lookup_order',
    description: 'Look up the status of an order.',
    inputSchema: z.object({
      orderId: z.string().describe('The order ID to look up'),
    }),
  },
);

const getPricing = tool(
  async (args: { product: string }) => {
    return { product: args.product, price: 99.99, discount: '10% off' };
  },
  {
    name: 'get_pricing',
    description: 'Get pricing information for a product.',
    inputSchema: z.object({
      product: z.string().describe('The product to get pricing for'),
    }),
  },
);

// -- Specialist agents -------------------------------------------------------

const billingAgent = new Agent({
  name: 'billing',
  model: llmModel,
  instructions: 'You handle billing questions: balances, payments, invoices.',
  tools: [checkBalance],
});

const technicalAgent = new Agent({
  name: 'technical',
  model: llmModel,
  instructions: 'You handle technical questions: order status, shipping, returns.',
  tools: [lookupOrder],
});

const salesAgent = new Agent({
  name: 'sales',
  model: llmModel,
  instructions: 'You handle sales questions: pricing, products, promotions.',
  tools: [getPricing],
});

// -- Orchestrator with handoffs -----------------------------------------------

const support = new Agent({
  name: 'support',
  model: llmModel,
  instructions:
    'Route customer requests to the right specialist: billing, technical, or sales.',
  agents: [billingAgent, technicalAgent, salesAgent],
  strategy: 'handoff',
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(
    support,
    "What's the balance on account ACC-123?",
  );
  result.printResult();
} finally {
  await runtime.shutdown();
}
