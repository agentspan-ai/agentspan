/**
 * 65 - Parallel Agents with Tools — each branch has its own tools.
 *
 * Both analysts run concurrently on the same input. Their results
 * are aggregated by the parent.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
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

// -- Parallel agents with tools ----------------------------------------------

export const financialAnalyst = new Agent({
  name: 'financial_analyst',
  model: llmModel,
  instructions:
    'You are a financial analyst. Use check_balance to look up the ' +
    'account mentioned. Report the balance and any financial observations.',
  tools: [checkBalance],
});

export const orderAnalyst = new Agent({
  name: 'order_analyst',
  model: llmModel,
  instructions:
    'You are an order analyst. Use lookup_order to check the order ' +
    'mentioned. Report the status and delivery timeline.',
  tools: [lookupOrder],
});

// Both analysts run concurrently
export const analysis = new Agent({
  name: 'parallel_analysis',
  model: llmModel,
  agents: [financialAnalyst, orderAnalyst],
  strategy: 'parallel',
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(analysis);
    await runtime.serve(analysis);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // analysis,
    // 'Check account ACC-200 balance and look up order ORD-300 status.',
    // );
    // result.printResult();

    // const output = String(result.output);
    // const checks: string[] = [];
    // if (output.includes('5432')) {
    // checks.push('[OK] Financial analyst retrieved balance');
    // } else {
    // checks.push('[WARN] Expected balance in output');
    // }
    // if (output.toLowerCase().includes('shipped')) {
    // checks.push('[OK] Order analyst retrieved order status');
    // } else {
    // checks.push('[WARN] Expected order status in output');
    // }
    // for (const c of checks) {
    // console.log(c);
    // }
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('65-parallel-with-tools.ts') || process.argv[1]?.endsWith('65-parallel-with-tools.js')) {
  main().catch(console.error);
}
