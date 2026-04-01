/**
 * Customer Service -- real-world multi-tool agent pattern.
 *
 * Demonstrates:
 *   - A single agent with multiple domain-specific tools
 *   - End-to-end customer inquiry handling
 *   - Account details, billing history, support tickets, plan updates
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Domain tools ──────────────────────────────────────────────────

const getAccountDetails = new FunctionTool({
  name: 'get_account_details',
  description: 'Retrieve account details for a customer.',
  parameters: z.object({
    account_id: z.string().describe('The account ID to look up'),
  }),
  execute: async (args: { account_id: string }) => {
    const accounts: Record<string, { name: string; email: string; plan: string; balance: number; status: string }> = {
      'ACC-001': {
        name: 'Alice Johnson',
        email: 'alice@example.com',
        plan: 'Premium',
        balance: 142.5,
        status: 'active',
      },
      'ACC-002': {
        name: 'Bob Martinez',
        email: 'bob@example.com',
        plan: 'Basic',
        balance: 0.0,
        status: 'active',
      },
    };
    return accounts[args.account_id.toUpperCase()] ?? { error: `Account ${args.account_id} not found` };
  },
});

const getBillingHistory = new FunctionTool({
  name: 'get_billing_history',
  description: 'Get billing history for an account.',
  parameters: z.object({
    account_id: z.string().describe('The account ID'),
    num_months: z.number().describe('Number of months of history').default(3),
  }),
  execute: async (args: { account_id: string; num_months?: number }) => {
    const numMonths = args.num_months ?? 3;
    const history: Record<string, Array<{ month: string; amount: number; status: string }>> = {
      'ACC-001': [
        { month: 'March 2025', amount: 49.99, status: 'paid' },
        { month: 'February 2025', amount: 49.99, status: 'paid' },
        { month: 'January 2025', amount: 42.5, status: 'paid' },
      ],
    };
    const records = history[args.account_id.toUpperCase()] ?? [];
    return { account_id: args.account_id, billing_history: records.slice(0, numMonths) };
  },
});

const submitSupportTicket = new FunctionTool({
  name: 'submit_support_ticket',
  description: 'Submit a support ticket for a customer issue.',
  parameters: z.object({
    account_id: z.string().describe('The account ID'),
    category: z.string().describe('Ticket category: "billing", "technical", "account", or "general"'),
    description: z.string().describe('Description of the issue'),
  }),
  execute: async (args: { account_id: string; category: string; description: string }) => {
    const validCategories = ['billing', 'technical', 'account', 'general'];
    if (!validCategories.includes(args.category.toLowerCase())) {
      return { error: `Invalid category. Must be one of: ${validCategories.join(', ')}` };
    }
    return {
      ticket_id: 'TKT-2025-0042',
      account_id: args.account_id,
      category: args.category,
      status: 'open',
      message: `Ticket created for ${args.category} issue`,
    };
  },
});

const updateAccountPlan = new FunctionTool({
  name: 'update_account_plan',
  description: 'Update the subscription plan for an account.',
  parameters: z.object({
    account_id: z.string().describe('The account ID'),
    new_plan: z.string().describe('New plan name: "basic", "premium", or "enterprise"'),
  }),
  execute: async (args: { account_id: string; new_plan: string }) => {
    const plans: Record<string, number> = { basic: 19.99, premium: 49.99, enterprise: 99.99 };
    const price = plans[args.new_plan.toLowerCase()];
    if (!price) {
      return { error: `Invalid plan. Available: ${Object.keys(plans).join(', ')}` };
    }
    return {
      status: 'success',
      account_id: args.account_id,
      new_plan: args.new_plan,
      new_price: `$${price}/month`,
      effective_date: 'Next billing cycle',
    };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'customer_service_rep',
  model,
  instruction:
    'You are a customer service representative for CloudServe Inc. ' +
    'Help customers with account inquiries, billing questions, plan changes, ' +
    'and support tickets. Always verify the account exists before making changes. ' +
    'Be professional and empathetic.',
  tools: [getAccountDetails, getBillingHistory, submitSupportTicket, updateAccountPlan],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    const result = await runtime.run(
    agent,
    "I'm customer ACC-001. Can you check my billing history and tell me my current plan? " +
    "I'm thinking about downgrading to the basic plan.",
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('16-customer-service.ts') || process.argv[1]?.endsWith('16-customer-service.js')) {
  main().catch(console.error);
}
