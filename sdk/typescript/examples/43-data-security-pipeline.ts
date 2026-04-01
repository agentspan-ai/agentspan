/**
 * 43 - Data Security Pipeline
 *
 * Demonstrates a sequential pipeline with data flow control where
 * sensitive information is collected, redacted, and then presented safely:
 *
 *   collector >> validator >> responder
 *
 * - collector: Fetches raw user data using tools (includes PII).
 * - validator: Redacts sensitive fields (SSN, balances, email) using tools.
 * - responder: Presents the safe, redacted data to the user.
 *
 * This pattern enforces a security boundary between data access and
 * user-facing responses, ensuring PII never reaches the final output.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Data tools ---------------------------------------------------------------

const fetchUserData = tool(
  async (args: { userId: string }) => {
    const users: Record<string, Record<string, unknown>> = {
      U001: {
        name: 'Alice Johnson',
        email: 'alice@example.com',
        role: 'admin',
        ssn_last4: '1234',
        account_balance: 15000.0,
      },
      U002: {
        name: 'Bob Smith',
        email: 'bob@example.com',
        role: 'user',
        ssn_last4: '5678',
        account_balance: 3200.0,
      },
    };
    return users[args.userId] ?? { error: `User ${args.userId} not found` };
  },
  {
    name: 'fetch_user_data',
    description: 'Fetch user data from the database.',
    inputSchema: z.object({
      userId: z.string().describe("The user's identifier"),
    }),
  },
);

// -- Redaction tools ----------------------------------------------------------

const redactSensitiveFields = tool(
  async (args: { data: string }) => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args.data) as Record<string, unknown>;
    } catch {
      return { error: 'Could not parse data for redaction' };
    }

    const sensitiveKeys = new Set(['ssn_last4', 'account_balance', 'email']);
    const redacted: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(parsed)) {
      redacted[k] = sensitiveKeys.has(k) ? '***REDACTED***' : v;
    }
    return { redacted_data: redacted };
  },
  {
    name: 'redact_sensitive_fields',
    description: 'Redact sensitive fields from data before responding to users.',
    inputSchema: z.object({
      data: z.string().describe('JSON string of user data to redact'),
    }),
  },
);

// -- Pipeline agents ----------------------------------------------------------

// Data collector fetches raw user data
export const collector = new Agent({
  name: 'data_collector',
  model: llmModel,
  instructions:
    'You are a data collection agent. When asked about a user, ' +
    'call fetch_user_data with their ID. Pass the raw data along ' +
    'to the next agent for security review.',
  tools: [fetchUserData],
});

// Validator enforces data security policy
export const validator = new Agent({
  name: 'security_validator',
  model: llmModel,
  instructions:
    'You are a security validator. Review data for sensitive information ' +
    '(SSN, account balances, email addresses). Use the redact_sensitive_fields ' +
    'tool to redact any sensitive data before passing it along. ' +
    'Only pass redacted data to the next agent.',
  tools: [redactSensitiveFields],
});

// Responder formats the final answer
export const responder = new Agent({
  name: 'responder',
  model: llmModel,
  instructions:
    'You are a customer service agent. Use the validated, redacted data ' +
    'to answer the user\'s question. NEVER reveal redacted information. ' +
    'If data shows ***REDACTED***, explain that the information is ' +
    'restricted for security reasons.',
});

// Sequential pipeline enforces data flow: collect -> validate -> respond
const pipeline = collector.pipe(validator).pipe(responder);

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(pipeline);
    // await runtime.serve(pipeline);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    pipeline,
    'Tell me everything about user U001 including their financial details.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('43-data-security-pipeline.ts') || process.argv[1]?.endsWith('43-data-security-pipeline.js')) {
  main().catch(console.error);
}
