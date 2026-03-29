/**
 * Safety Guardrails -- global safety enforcement using PII detection.
 *
 * Demonstrates:
 *   - Output guardrails that evaluate every agent response
 *   - Combining multiple safety checks (PII detection, sanitization)
 *   - Using sequential pipeline to enforce guardrails
 *
 * Inspired by the Google ADK safety-plugins sample which uses
 * BasePlugin for global safety. We use guardrails + sequential agents.
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

const checkPii = new FunctionTool({
  name: 'check_pii',
  description: 'Check text for personally identifiable information (PII).',
  parameters: z.object({
    text: z.string().describe('The text to scan for PII'),
  }),
  execute: async (args: { text: string }) => {
    const patterns: Record<string, RegExp> = {
      email: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
      phone: /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
      ssn: /\b\d{3}-\d{2}-\d{4}\b/g,
      credit_card: /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
    };

    const found: Record<string, number> = {};
    for (const [piiType, pattern] of Object.entries(patterns)) {
      const matches = args.text.match(pattern);
      if (matches && matches.length > 0) {
        found[piiType] = matches.length;
      }
    }

    return {
      has_pii: Object.keys(found).length > 0,
      pii_types: found,
      text_length: args.text.length,
    };
  },
});

const sanitizeResponse = new FunctionTool({
  name: 'sanitize_response',
  description: 'Remove or mask PII from a response before delivering to user.',
  parameters: z.object({
    text: z.string().describe('The response text to sanitize'),
    pii_types: z.string().describe('Comma-separated PII types detected').default(''),
  }),
  execute: async (args: { text: string; pii_types?: string }) => {
    let sanitized = args.text;
    sanitized = sanitized.replace(
      /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
      '[EMAIL REDACTED]',
    );
    sanitized = sanitized.replace(/\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g, '[PHONE REDACTED]');
    sanitized = sanitized.replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[SSN REDACTED]');
    sanitized = sanitized.replace(
      /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
      '[CARD REDACTED]',
    );

    return { sanitized_text: sanitized, was_modified: sanitized !== args.text };
  },
});

// ── Pipeline stages ──────────────────────────────────────────────────

// Main assistant generates responses
export const assistant = new LlmAgent({
  name: 'helpful_assistant',
  model,
  instruction:
    'You are a helpful customer service assistant. Answer questions ' +
    'about account details, contact information, and general inquiries. ' +
    'When providing information, include relevant details.',
});

// Safety checker scans the response
export const safetyChecker = new LlmAgent({
  name: 'safety_checker',
  model,
  instruction:
    "You are a safety reviewer. Check the previous agent's response " +
    'for any PII (emails, phone numbers, SSNs, credit card numbers). ' +
    'Use check_pii on the response text. If PII is found, use ' +
    'sanitize_response to clean it. Pass the clean version along.',
  tools: [checkPii, sanitizeResponse],
});

// Pipeline: generate -> check -> deliver
export const safePipeline = new SequentialAgent({
  name: 'safe_assistant',
  subAgents: [assistant, safetyChecker],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(safePipeline);
    await runtime.serve(safePipeline);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // safePipeline,
    // 'What are the contact details for our support team? ' +
    // 'Include email support@company.com and phone 555-123-4567.',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('26-safety-guardrails.ts') || process.argv[1]?.endsWith('26-safety-guardrails.js')) {
  main().catch(console.error);
}
