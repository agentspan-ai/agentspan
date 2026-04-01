/**
 * 10 - Guardrails — output validation with tool calls.
 *
 * Demonstrates guardrails that catch PII leaking from tool results into
 * the agent's final answer. The agent uses two tools:
 *
 * 1. get_order_status  — returns safe order data (no PII)
 * 2. get_customer_info — returns data that includes a credit card number
 *
 * Three guardrail types are shown:
 * - RegexGuardrail: server-side pattern matching to block PII
 * - LLMGuardrail: LLM-based policy check for sensitive data
 * - Custom guardrail function (via guardrail())
 *
 * The RegexGuardrail is the primary PII blocker (runs server-side).
 * If the agent includes the raw credit card number in its response,
 * the guardrail fails with onFail="retry" — the agent retries with
 * feedback asking it to redact the PII.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  RegexGuardrail,
  LLMGuardrail,
  guardrail,
  tool,
} from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';
import { llmModel } from './settings.js';

// ── Tools ─────────────────────────────────────────────────

const getOrderStatus = tool(
  async (args: { orderId: string }) => {
    return {
      order_id: args.orderId,
      status: 'shipped',
      tracking: '1Z999AA10123456784',
      estimated_delivery: '2026-02-22',
    };
  },
  {
    name: 'get_order_status',
    description: 'Look up the current status of an order.',
    inputSchema: z.object({
      orderId: z.string().describe('The order ID to look up'),
    }),
  },
);

const getCustomerInfo = tool(
  async (args: { customerId: string }) => {
    // This tool returns data with PII — the guardrail should catch it
    // if the agent includes it verbatim in the response.
    return {
      customer_id: args.customerId,
      name: 'Alice Johnson',
      email: 'alice@example.com',
      card_on_file: '4532-0150-1234-5678', // PII!
      membership: 'gold',
    };
  },
  {
    name: 'get_customer_info',
    description: 'Retrieve customer details including payment info on file.',
    inputSchema: z.object({
      customerId: z.string().describe('The customer ID to look up'),
    }),
  },
);

// ── RegexGuardrail: block PII patterns (server-side) ──────

const piiBlocker = new RegexGuardrail({
  name: 'pii_blocker',
  patterns: [
    '\\b\\d{3}-\\d{2}-\\d{4}\\b',                      // SSN
    '\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b', // Credit card
  ],
  mode: 'block',
  position: 'output',
  onFail: 'retry',
  message: 'PII detected (credit card or SSN). Please redact all personal information.',
});

// ── LLMGuardrail: policy-based sensitive data check ───────

const sensitiveDataChecker = new LLMGuardrail({
  name: 'sensitive_data_checker',
  model: 'openai/gpt-4o-mini',
  policy:
    'Check if the response contains any sensitive personal information ' +
    'such as full credit card numbers, SSNs, or passwords. ' +
    'If found, request redaction.',
  position: 'output',
  onFail: 'fix',
  maxTokens: 5000,
});

// ── Custom guardrail function (local validation logic) ────

const noPii = guardrail(
  (content: string): GuardrailResult => {
    const ccPattern = /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/;
    const ssnPattern = /\b\d{3}-\d{2}-\d{4}\b/;

    if (ccPattern.test(content) || ssnPattern.test(content)) {
      return {
        passed: false,
        message:
          'Your response contains PII (credit card or SSN). ' +
          'Redact all card numbers and SSNs before responding.',
      };
    }
    return { passed: true };
  },
  {
    name: 'no_pii',
    position: 'output',
    onFail: 'retry',
  },
);

// ── Agent ─────────────────────────────────────────────────

export const agent = new Agent({
  name: 'support_agent',
  model: llmModel,
  tools: [getOrderStatus, getCustomerInfo],
  instructions:
    'You are a customer support assistant. Use the available tools to ' +
    'answer questions about orders and customers. Always include all ' +
    'details from the tool results in your response.',
  // ^^^ This instruction deliberately encourages the agent to include
  // raw tool output, which will trigger the guardrail on the second
  // tool call's PII data.
  guardrails: [
    piiBlocker.toGuardrailDef(),
    sensitiveDataChecker.toGuardrailDef(),
    noPii,
  ],
});

// ── Run ───────────────────────────────────────────────────

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
    // This prompt triggers both tools:
    //   1. get_order_status("ORD-42")   → safe data, passes guardrail
    //   2. get_customer_info("CUST-7")  → contains credit card, trips guardrail
    const result = await runtime.run(
    agent,
    'I need a full summary: What\'s the status of order ORD-42, ' +
    'and what\'s the profile for customer CUST-7?',
    );
    result.printResult();

    // Verify the guardrail worked — no raw card number in the output
    if (result.output && String(result.output).includes('4532-0150-1234-5678')) {
    console.log('[WARN] PII leaked through the guardrail!');
    } else {
    console.log('[OK] PII was redacted from the final output.');
    }
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('10-guardrails.ts') || process.argv[1]?.endsWith('10-guardrails.js')) {
  main().catch(console.error);
}
