/**
 * Handoffs — agent delegating to sub-agents.
 *
 * Demonstrates the handoff strategy where the parent agent's LLM decides
 * which sub-agent to delegate to. Sub-agents appear as callable tools.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Sub-agent tools --------------------------------------------------------

const checkBalance = tool(
  async (args: { accountId: string }) => {
    return { account_id: args.accountId, balance: 5432.10, currency: 'USD' };
  },
  {
    name: 'check_balance',
    description: 'Check the balance of a bank account.',
    inputSchema: {
      type: 'object',
      properties: {
        accountId: { type: 'string', description: 'The account ID to check' },
      },
      required: ['accountId'],
    },
  },
);

const lookupOrder = tool(
  async (args: { orderId: string }) => {
    return { order_id: args.orderId, status: 'shipped', eta: '2 days' };
  },
  {
    name: 'lookup_order',
    description: 'Look up the status of an order.',
    inputSchema: {
      type: 'object',
      properties: {
        orderId: { type: 'string', description: 'The order ID to look up' },
      },
      required: ['orderId'],
    },
  },
);

const getPricing = tool(
  async (args: { product: string }) => {
    return { product: args.product, price: 99.99, discount: '10% off' };
  },
  {
    name: 'get_pricing',
    description: 'Get pricing information for a product.',
    inputSchema: {
      type: 'object',
      properties: {
        product: { type: 'string', description: 'The product to get pricing for' },
      },
      required: ['product'],
    },
  },
);

// -- Specialist agents -------------------------------------------------------

export const billingAgent = new Agent({
  name: 'billing',
  model: llmModel,
  instructions: 'You handle billing questions: balances, payments, invoices.',
  tools: [checkBalance],
});

export const technicalAgent = new Agent({
  name: 'technical',
  model: llmModel,
  instructions: 'You handle technical questions: order status, shipping, returns.',
  tools: [lookupOrder],
});

export const salesAgent = new Agent({
  name: 'sales',
  model: llmModel,
  instructions: 'You handle sales questions: pricing, products, promotions.',
  tools: [getPricing],
});

// -- Orchestrator with handoffs -----------------------------------------------

export const support = new Agent({
  name: 'support',
  model: llmModel,
  instructions:
    'Route customer requests to the right specialist: billing, technical, or sales.',
  agents: [billingAgent, technicalAgent, salesAgent],
  strategy: 'handoff',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    support,
    "What's the balance on account ACC-123?",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(support);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents support
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(support);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
