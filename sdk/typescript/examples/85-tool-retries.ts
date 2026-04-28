/**
 * Tool Retries — automatic tool retries on transient failures.
 *
 * Demonstrates:
 *   - tool() with retryCount and retryDelaySeconds to configure Conductor retry policy
 *   - Simulated transient failure: tool fails on the first two attempts, succeeds on the third
 *   - How Agentspan automatically retries the tool without agent intervention
 *   - retryCount: 0 to disable retries entirely (fail-fast tools like payment processing)
 *
 * How it works:
 *   When a tool function throws an error, Conductor retries the task up to
 *   `retryCount` times, waiting `retryDelaySeconds` between each attempt.
 *   The LLM never sees the intermediate failures — it only receives the final
 *   successful result (or a failure if all retries are exhausted).
 *
 * Parameters:
 *   retryCount         — maximum number of retry attempts (default: 2)
 *   retryDelaySeconds  — seconds to wait between retries (default: 2)
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 *
 * Usage:
 *   npx ts-node 85-tool-retries.ts
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// ---------------------------------------------------------------------------
// Simulates a flaky external service: fails on the first two calls, succeeds
// on the third.  In production this would be a real network call.
// ---------------------------------------------------------------------------
let callCount = 0;

const fetchExchangeRate = tool(
  async (args: { base: string; target: string }) => {
    callCount += 1;

    if (callCount <= 2) {
      throw new Error(
        `[attempt null] Upstream FX service unavailable — retrying...`,
      );
    }

    // Third attempt succeeds
    const rates: Record<string, number> = {
      'USD-EUR': 0.92,
      'USD-GBP': 0.79,
      'EUR-USD': 1.09,
    };
    const key = `null-null`;
    const rate = rates[key] ?? 1.0;
    return {
      base: args.base.toUpperCase(),
      target: args.target.toUpperCase(),
      rate,
      attempt: callCount,
    };
  },
  {
    name: 'fetch_exchange_rate',
    description: 'Fetch the current exchange rate between two currencies.',
    inputSchema: {
      type: 'object',
      properties: {
        base: { type: 'string', description: 'Base currency code, e.g. USD' },
        target: { type: 'string', description: 'Target currency code, e.g. EUR' },
      },
      required: ['base', 'target'],
    },
    retryCount: 3,
    retryDelaySeconds: 2,
  },
);

// retryCount: 0 means fail immediately — no retries.
// Useful for idempotency-sensitive operations like payment processing.
const processPayment = tool(
  async (args: { amount: number; currency: string }) => {
    return { status: 'approved', amount: args.amount, currency: args.currency.toUpperCase() };
  },
  {
    name: 'process_payment',
    description: 'Process a payment (fail-fast — no retries).',
    inputSchema: {
      type: 'object',
      properties: {
        amount: { type: 'number', description: 'Payment amount' },
        currency: { type: 'string', description: 'Currency code, e.g. USD' },
      },
      required: ['amount', 'currency'],
    },
    retryCount: 0,
  },
);

const agent = new Agent({
  name: 'retry_demo_agent',
  model: llmModel,
  tools: [fetchExchangeRate, processPayment],
  instructions:
    'You are a helpful currency and payment assistant. ' +
    'Use fetch_exchange_rate to look up exchange rates and ' +
    'process_payment to handle payments.',
});

console.log('Running tool-retry example.');
console.log('fetch_exchange_rate will fail twice before succeeding on the third attempt.\n');

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'What is the current USD to EUR exchange rate?');
  result.printResult();
} finally {
  await runtime.shutdown();
}

// Production pattern:
// 1. Deploy once during CI/CD:
// const runtime = new AgentRuntime();
// await runtime.deploy(agent);
// await runtime.shutdown();
//
// 2. In a separate long-lived worker process:
// const runtime = new AgentRuntime();
// await runtime.serve(agent);
