/**
 * Multi-Step Tool Calling — chained lookups and calculations.
 *
 * The agent has four tools. The prompt requires it to:
 * 1. Look up a customer's account
 * 2. Fetch their recent transactions
 * 3. Calculate the total spend
 * 4. Formulate a final answer using all the data
 *
 * This shows the agent loop in action: the LLM calls tools one at a
 * time, feeds each result into the next decision, and stops when it has
 * enough information to answer.
 *
 * In the Conductor UI you'll see each tool call as a separate DynamicTask
 * with clear inputs/outputs, making it easy to trace the reasoning chain.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

const lookupCustomer = tool(
  async (args: { email: string }) => {
    const customers: Record<string, { id: string; name: string; tier: string }> = {
      'alice@example.com': { id: 'CUST-001', name: 'Alice Johnson', tier: 'gold' },
      'bob@example.com': { id: 'CUST-002', name: 'Bob Smith', tier: 'silver' },
    };
    return customers[args.email] ?? { error: `No customer found for ${args.email}` };
  },
  {
    name: 'lookup_customer',
    description: 'Look up a customer by email address.',
    inputSchema: z.object({
      email: z.string().describe('Customer email address'),
    }),
  },
);

const getTransactions = tool(
  async (args: { customer_id: string; limit: number }) => {
    const transactions: Record<string, Array<{ date: string; amount: number; merchant: string }>> = {
      'CUST-001': [
        { date: '2026-02-15', amount: 120.0, merchant: 'Cloud Services Inc' },
        { date: '2026-02-12', amount: 45.5, merchant: 'Office Supplies Co' },
        { date: '2026-02-10', amount: 230.0, merchant: 'Dev Tools Ltd' },
      ],
    };
    const txns = transactions[args.customer_id] ?? [];
    return { customer_id: args.customer_id, transactions: txns.slice(0, args.limit) };
  },
  {
    name: 'get_transactions',
    description: 'Get recent transactions for a customer.',
    inputSchema: z.object({
      customer_id: z.string().describe('Customer ID'),
      limit: z.number().describe('Maximum number of transactions to return'),
    }),
  },
);

const calculateTotal = tool(
  async (args: { amounts: number[] }) => {
    const total = args.amounts.reduce((sum, a) => sum + a, 0);
    return { total: Math.round(total * 100) / 100, count: args.amounts.length };
  },
  {
    name: 'calculate_total',
    description: 'Calculate the sum of a list of amounts.',
    inputSchema: z.object({
      amounts: z.array(z.number()).describe('List of amounts to sum'),
    }),
  },
);

const sendSummaryEmail = tool(
  async (args: { to: string; subject: string; body: string }) => {
    return { status: 'sent', to: args.to, subject: args.subject };
  },
  {
    name: 'send_summary_email',
    description: 'Send a summary email to a customer.',
    inputSchema: z.object({
      to: z.string().describe('Recipient email address'),
      subject: z.string().describe('Email subject'),
      body: z.string().describe('Email body'),
    }),
  },
);

export const agent = new Agent({
  name: 'account_analyst',
  model: llmModel,
  tools: [lookupCustomer, getTransactions, calculateTotal, sendSummaryEmail],
  instructions:
    'You are an account analyst. When asked about a customer, look them up, ' +
    'fetch their transactions, calculate the total, and provide a summary. ' +
    'Use the tools step by step.',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    agent,
    'How much has alice@example.com spent recently? ' +
    'Get her last 3 transactions and give me the total.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('02b-multi-step-tools.ts') || process.argv[1]?.endsWith('02b-multi-step-tools.js')) {
  main().catch(console.error);
}
