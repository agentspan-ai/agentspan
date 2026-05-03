/**
 * Retry Configuration — controlling how Conductor retries failed tool executions.
 *
 * Demonstrates three retry strategies:
 *   - FIXED: constant delay between retries (default when not specified)
 *   - LINEAR_BACKOFF: delay increases linearly (delay × attempt_number)
 *   - EXPONENTIAL_BACKOFF: delay increases exponentially (delay × 2^attempt_number)
 *
 * Also shows retryCount=0 to disable retries entirely (fail immediately on first error).
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for agentspan path
 *   - AGENTSPAN_LLM_MODEL for the LLM model
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '@agentspan-ai/sdk';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

// Custom retry with default FIXED strategy (10 retries, 5s delay)
const fetchData = new FunctionTool({
  name: 'fetch_data',
  description: 'Fetch data from a remote source with fixed retry strategy.',
  parameters: z.object({
    query: z.string().describe('The query to fetch data for'),
  }),
  retryCount: 10,
  retryDelaySeconds: 5,
  execute: async (args: { query: string }) => {
    return { query: args.query, data: `Fetched data for: null` };
  },
});

// Linear backoff (5 retries, 2s base delay → 2s, 4s, 6s, 8s, 10s)
const callApi = new FunctionTool({
  name: 'call_api',
  description: 'Call an external API with linear backoff retry strategy.',
  parameters: z.object({
    endpoint: z.string().describe('The API endpoint to call'),
  }),
  retryCount: 5,
  retryDelaySeconds: 2,
  retryLogic: 'LINEAR_BACKOFF',
  execute: async (args: { endpoint: string }) => {
    return { endpoint: args.endpoint, status: 'ok', response: 'API response' };
  },
});

// Exponential backoff (3 retries, 1s base delay → 1s, 2s, 4s)
const processPayment = new FunctionTool({
  name: 'process_payment',
  description: 'Process a payment with exponential backoff retry strategy.',
  parameters: z.object({
    amount: z.number().describe('The payment amount in USD'),
  }),
  retryCount: 3,
  retryDelaySeconds: 1,
  retryLogic: 'EXPONENTIAL_BACKOFF',
  execute: async (args: { amount: number }) => {
    return { amount: args.amount, status: 'processed', transactionId: 'txn-001' };
  },
});

// No retries — fail immediately on first error
const validateInput = new FunctionTool({
  name: 'validate_input',
  description: 'Validate input data — no retries on failure.',
  parameters: z.object({
    data: z.string().describe('The data to validate'),
  }),
  retryCount: 0,
  execute: async (args: { data: string }) => {
    if (!args.data) {
      throw new Error('Input data cannot be empty');
    }
    return { data: args.data, valid: true };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'retry_demo',
  model,
  instruction:
    'You are a demo agent showcasing retry configuration. ' +
    'Use the available tools to demonstrate different retry strategies.',
  tools: [fetchData, callApi, processPayment, validateInput],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      'Demo retry configuration by fetching data and calling an API',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents retry_demo
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
