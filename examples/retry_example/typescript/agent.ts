/**
 * Retry Example — automatic tool retries on transient failures.
 *
 * Demonstrates:
 *   - tool() with retryCount and retryDelaySeconds
 *   - Simulated transient failure that succeeds after retries
 *   - How Agentspan automatically retries the tool without agent intervention
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';

// Simulates a flaky external service: fails on the first two calls, succeeds on the third.
let callCount = 0;

const fetchExchangeRate = tool(
  async (args: { base: string; target: string }) => {
    callCount += 1;

    if (callCount <= 2) {
      throw new Error(
        `[attempt null] Upstream service unavailable — retrying...`,
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
    return { base: args.base.toUpperCase(), target: args.target.toUpperCase(), rate, attempt: callCount };
  },
  {
    name: 'fetch_exchange_rate',
    description: 'Fetch the exchange rate between two currencies.',
    inputSchema: {
      type: 'object',
      properties: {
        base:   { type: 'string', description: 'Base currency code, e.g. USD' },
        target: { type: 'string', description: 'Target currency code, e.g. EUR' },
      },
      required: ['base', 'target'],
    },
    retryCount: 3,
    retryDelaySeconds: 1,
  },
);

const agent = new Agent({
  name: 'exchange_rate_agent',
  model: process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o-mini',
  tools: [fetchExchangeRate],
  instructions: 'You are a helpful currency assistant. Use the fetch_exchange_rate tool to answer questions.',
});

console.log('Running retry example — the tool will fail twice before succeeding.\n');
const runtime = new AgentRuntime();
try {
  const result = await runtime.run(agent, 'What is the current USD to EUR exchange rate?');
  result.printResult();
} finally {
  await runtime.shutdown();
}
