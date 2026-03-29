// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent with Guardrails -- input and output validation.
 *
 * Demonstrates:
 *   - Input guardrails that validate user messages before processing
 *   - Output guardrails that validate agent responses
 *   - Running via Agentspan passthrough
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import {
  Agent,
  tool,
  setTracingDisabled,
} from '@openai/agents';
import type { InputGuardrail, OutputGuardrail, GuardrailFunctionOutput } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Tools ───────────────────────────────────────────────────────────

const getAccountBalance = tool({
  name: 'get_account_balance',
  description: 'Look up the balance of a bank account.',
  parameters: z.object({ account_id: z.string().describe('Account ID') }),
  execute: async ({ account_id }) => {
    const accounts: Record<string, string> = {
      'ACC-100': '$5,230.00',
      'ACC-200': '$12,750.50',
      'ACC-300': '$890.25',
    };
    return accounts[account_id] ?? `Account ${account_id} not found`;
  },
});

const transferFunds = tool({
  name: 'transfer_funds',
  description: 'Transfer funds between accounts.',
  parameters: z.object({
    from_account: z.string().describe('Source account'),
    to_account: z.string().describe('Destination account'),
    amount: z.number().describe('Amount to transfer'),
  }),
  execute: async ({ from_account, to_account, amount }) => {
    return `Transferred $${amount.toFixed(2)} from ${from_account} to ${to_account}.`;
  },
});

// ── Guardrails ──────────────────────────────────────────────────────

const checkForPii: InputGuardrail = {
  name: 'check_for_pii',
  execute: async ({ input }): Promise<GuardrailFunctionOutput> => {
    const inputText = typeof input === 'string' ? input : JSON.stringify(input);

    // Check for SSN patterns
    const ssnPattern = /\b\d{3}-\d{2}-\d{4}\b/;
    if (ssnPattern.test(inputText)) {
      return {
        outputInfo: { reason: 'SSN detected in input' },
        tripwireTriggered: true,
      };
    }

    // Check for credit card patterns
    const ccPattern = /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/;
    if (ccPattern.test(inputText)) {
      return {
        outputInfo: { reason: 'Credit card number detected in input' },
        tripwireTriggered: true,
      };
    }

    return {
      outputInfo: { reason: 'No PII detected' },
      tripwireTriggered: false,
    };
  },
};

const checkOutputSafety: OutputGuardrail = {
  name: 'check_output_safety',
  execute: async ({ agentOutput }): Promise<GuardrailFunctionOutput> => {
    const outputText = String(agentOutput).toLowerCase();

    const forbiddenPhrases = [
      'internal system',
      'database password',
      'api key',
      'secret token',
    ];

    for (const phrase of forbiddenPhrases) {
      if (outputText.includes(phrase)) {
        return {
          outputInfo: { reason: `Forbidden phrase detected: '${phrase}'` },
          tripwireTriggered: true,
        };
      }
    }

    return {
      outputInfo: { reason: 'Output is safe' },
      tripwireTriggered: false,
    };
  },
};

// ── Agent with guardrails ───────────────────────────────────────────

export const agent = new Agent({
  name: 'banking_assistant',
  instructions:
    'You are a secure banking assistant. Help users check account balances ' +
    'and transfer funds. Never reveal internal system details.',
  model: 'gpt-4o-mini',
  tools: [getAccountBalance, transferFunds],
  inputGuardrails: [checkForPii],
  outputGuardrails: [checkOutputSafety],
});

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(agent, "What's the balance on account ACC-100?");
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('05-guardrails.ts') || process.argv[1]?.endsWith('05-guardrails.js')) {
  main().catch(console.error);
}
