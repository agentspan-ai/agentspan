/**
 * CaMeL-inspired Security Policy Agent -- controlled data flow.
 *
 * Demonstrates:
 *   - Multi-agent system with security policy enforcement
 *   - Guardrails to prevent sensitive data leakage
 *   - Sequential pipeline: collector -> validator -> responder
 *
 * Inspired by the Google ADK camel sample which uses CaMeL framework
 * for secure, controlled LLM agent data flow.
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, SequentialAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const fetchUserData = new FunctionTool({
  name: 'fetch_user_data',
  description: 'Fetch user data from the database.',
  parameters: z.object({
    user_id: z.string().describe("The user's identifier"),
  }),
  execute: async (args: { user_id: string }) => {
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
    return users[args.user_id] ?? { error: `User ${args.user_id} not found` };
  },
});

const redactSensitiveFields = new FunctionTool({
  name: 'redact_sensitive_fields',
  description: 'Redact sensitive fields from data before responding to users.',
  parameters: z.object({
    data: z.string().describe('JSON string of user data to redact'),
  }),
  execute: async (args: { data: string }) => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args.data);
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
});

// ── Pipeline stages ──────────────────────────────────────────────────

// Data collector fetches raw user data
export const collector = new LlmAgent({
  name: 'data_collector',
  model,
  instruction:
    'You are a data collection agent. When asked about a user, ' +
    'call fetch_user_data with their ID. Pass the raw data along ' +
    'to the next agent for security review.',
  tools: [fetchUserData],
});

// Validator enforces data security policy
export const validator = new LlmAgent({
  name: 'security_validator',
  model,
  instruction:
    'You are a security validator. Review data for sensitive information ' +
    '(SSN, account balances, email addresses). Use the redact_sensitive_fields ' +
    'tool to redact any sensitive data before passing it along. ' +
    'Only pass redacted data to the next agent.',
  tools: [redactSensitiveFields],
});

// Responder formats the final answer
export const responder = new LlmAgent({
  name: 'responder',
  model,
  instruction:
    'You are a customer service agent. Use the validated, redacted data ' +
    'to answer the user\'s question. NEVER reveal redacted information. ' +
    'If data shows ***REDACTED***, explain that the information is ' +
    'restricted for security reasons.',
});

// Sequential pipeline enforces data flow: collect -> validate -> respond
export const pipeline = new SequentialAgent({
  name: 'secure_data_pipeline',
  subAgents: [collector, validator, responder],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(pipeline);
    await runtime.serve(pipeline);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // pipeline,
    // 'Tell me everything about user U001 including their financial details.',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('25-camel-security.ts') || process.argv[1]?.endsWith('25-camel-security.js')) {
  main().catch(console.error);
}
