/**
 * Credentials -- non-isolated tools using getCredential().
 *
 * Demonstrates:
 *   - tool() with isolated: false, credentials: ["STRIPE_SECRET_KEY"]
 *   - getCredential() to access the injected value in-process
 *   - When to use isolated=false: SDK clients that can't be serialized across
 *     subprocess boundaries (e.g. existing SDK objects, shared state)
 *   - CredentialNotFoundError handling for graceful degradation
 *
 * When to use isolated=false vs isolated=true (default):
 *   isolated=true  -- runs tool in a fresh subprocess; safer (no env bleed
 *                     between concurrent tasks); use for shell commands, scripts
 *   isolated=false -- runs tool in the same worker process; use only when the
 *                     tool holds shared state or uses objects that can't be
 *                     serialized (e.g. database connection pools, SDK clients)
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - STRIPE_SECRET_KEY stored: agentspan credentials set STRIPE_SECRET_KEY <your-stripe-secret-key>
 */

import {
  Agent,
  AgentRuntime,
  CredentialNotFoundError,
  getCredential,
  tool,
} from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Non-isolated tool: get Stripe customer balance ---------------------------

const getCustomerBalance = tool(
  async (args: { customerId: string }) => {
    let apiKey: string;
    try {
      apiKey = await getCredential('STRIPE_SECRET_KEY');
    } catch (err) {
      if (err instanceof CredentialNotFoundError) {
        return {
          error: 'STRIPE_SECRET_KEY not configured -- run: agentspan credentials set STRIPE_SECRET_KEY', <your-stripe-secret-key',>
        };
      }
      throw err;
    }

    const auth = Buffer.from(`${apiKey}:`).toString('base64');
    try {
      const resp = await fetch(
        `https://api.stripe.com/v1/customers/${args.customerId}`,
        {
          headers: { Authorization: `Basic ${auth}` },
          signal: AbortSignal.timeout(10_000),
        },
      );
      if (!resp.ok) {
        return { error: `Stripe API error ${resp.status}: ${resp.statusText}` };
      }
      const customer = (await resp.json()) as Record<string, unknown>;
      return {
        customer_id: args.customerId,
        name: customer.name,
        balance: ((customer.balance as number) ?? 0) / 100, // cents -> dollars
        currency: ((customer.currency as string) ?? 'usd').toUpperCase(),
      };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'get_customer_balance',
    description: 'Look up a Stripe customer balance. Uses getCredential() for in-process access.',
    inputSchema: {
      type: 'object',
      properties: {
        customerId: { type: 'string', description: 'Stripe customer ID' },
      },
      required: ['customerId'],
    },
    isolated: false,
    credentials: ['STRIPE_SECRET_KEY'],
  },
);

// -- Non-isolated tool: list recent Stripe charges ----------------------------

const listRecentCharges = tool(
  async (args: { limit?: number }) => {
    let apiKey: string;
    try {
      apiKey = await getCredential('STRIPE_SECRET_KEY');
    } catch (err) {
      if (err instanceof CredentialNotFoundError) {
        return { error: 'STRIPE_SECRET_KEY not configured' };
      }
      throw err;
    }

    const limit = Math.min(args.limit ?? 5, 20);
    const auth = Buffer.from(`${apiKey}:`).toString('base64');
    try {
      const resp = await fetch(
        `https://api.stripe.com/v1/charges?limit=${limit}`,
        {
          headers: { Authorization: `Basic ${auth}` },
          signal: AbortSignal.timeout(10_000),
        },
      );
      if (!resp.ok) {
        return { error: `Stripe API error ${resp.status}: ${resp.statusText}` };
      }
      const data = (await resp.json()) as { data?: Array<Record<string, unknown>> };
      const charges = data.data ?? [];
      return {
        charges: charges.map((c) => ({
          id: c.id,
          amount: (c.amount as number) / 100,
          currency: (c.currency as string).toUpperCase(),
          status: c.status,
          description: c.description,
        })),
      };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'list_recent_charges',
    description: 'List the most recent Stripe charges.',
    inputSchema: {
      type: 'object',
      properties: {
        limit: { type: 'number', description: 'Number of charges to return (max 20)' },
      },
    },
    isolated: false,
    credentials: ['STRIPE_SECRET_KEY'],
  },
);

// -- Agent definition ---------------------------------------------------------

export const agent = new Agent({
  name: 'billing_agent',
  model: llmModel,
  tools: [getCustomerBalance, listRecentCharges],
  credentials: ['STRIPE_SECRET_KEY'],
  instructions:
    'You are a billing assistant with access to Stripe. ' +
    'Help users look up customer balances and recent charges.',
});

// -- Run ----------------------------------------------------------------------

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Show me the 3 most recent charges.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents billing_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
