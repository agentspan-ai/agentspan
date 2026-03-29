/**
 * 64 - Swarm with Tools — sub-agents have their own domain tools.
 *
 * Extends the basic swarm pattern by giving each specialist its own tools.
 * The LLM can call domain tools AND transfer tools in the same turn.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, OnTextMention, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Domain tools ------------------------------------------------------------

const checkBalance = tool(
  async (args: { accountId: string }) => {
    return { account_id: args.accountId, balance: 5432.10, currency: 'USD' };
  },
  {
    name: 'check_balance',
    description: 'Check the balance of a bank account.',
    inputSchema: z.object({
      accountId: z.string().describe('The bank account ID'),
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
      orderId: z.string().describe('The order ID'),
    }),
  },
);

// -- Specialist agents with tools --------------------------------------------

export const billingSpecialist = new Agent({
  name: 'billing_specialist',
  model: llmModel,
  instructions:
    'You are a billing specialist. Use the check_balance tool to look up ' +
    'account balances. Include the balance amount in your response.',
  tools: [checkBalance],
});

export const orderSpecialist = new Agent({
  name: 'order_specialist',
  model: llmModel,
  instructions:
    'You are an order specialist. Use the lookup_order tool to check ' +
    'order status. Include the shipping status and ETA in your response.',
  tools: [lookupOrder],
});

// -- Front-line support with swarm handoffs ----------------------------------

export const support = new Agent({
  name: 'support',
  model: llmModel,
  instructions:
    'You are front-line customer support. Triage customer requests. ' +
    'Transfer to billing_specialist for account/payment questions, ' +
    'order_specialist for shipping/order questions.',
  agents: [billingSpecialist, orderSpecialist],
  strategy: 'swarm',
  handoffs: [
    new OnTextMention({ text: 'billing', target: 'billing_specialist' }),
    new OnTextMention({ text: 'order', target: 'order_specialist' }),
  ],
  maxTurns: 3,
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(support);
    await runtime.serve(support);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // // Scenario 1: Billing question
    // console.log('='.repeat(60));
    // console.log('  Scenario 1: Billing question (swarm -> billing + tool)');
    // console.log('='.repeat(60));
    // const result = await runtime.run(support, "What's the balance on account ACC-456?");
    // result.printResult();

    // const output = String(result.output);
    // if (output.includes('5432')) {
    // console.log('[OK] Billing specialist used check_balance tool');
    // } else {
    // console.log('[WARN] Expected balance amount in output');
    // }

    // // Scenario 2: Order question
    // console.log('\n' + '='.repeat(60));
    // console.log('  Scenario 2: Order question (swarm -> order + tool)');
    // console.log('='.repeat(60));
    // const result2 = await runtime.run(support, 'Where is my order ORD-789?');
    // result2.printResult();

    // const output2 = String(result2.output);
    // if (output2.toLowerCase().includes('shipped')) {
    // console.log('[OK] Order specialist used lookup_order tool');
    // } else {
    // console.log('[WARN] Expected shipping status in output');
    // }
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('64-swarm-with-tools.ts') || process.argv[1]?.endsWith('64-swarm-with-tools.js')) {
  main().catch(console.error);
}
