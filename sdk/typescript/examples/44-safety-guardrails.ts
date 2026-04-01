/**
 * 44 - Safety Guardrails Pipeline
 *
 * Demonstrates a sequential pipeline where a safety checker agent scans
 * the primary agent's output for PII and sanitizes it before delivery:
 *
 *   assistant >> safetyChecker
 *
 * - assistant: A helpful agent that answers questions (may include PII).
 * - safetyChecker: Scans the response for PII (emails, phones, SSNs,
 *   credit cards) using regex-based tools and sanitizes any matches.
 *
 * This pattern uses tool-based PII detection rather than the built-in
 * guardrail system, showing how sequential agents can enforce safety
 * policies through explicit scanning and redaction.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Safety tools -------------------------------------------------------------

const checkPii = tool(
  async (args: { text: string }) => {
    const patterns: Record<string, RegExp> = {
      email: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
      phone: /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
      ssn: /\b\d{3}-\d{2}-\d{4}\b/g,
      credit_card: /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
    };

    const found: Record<string, number> = {};
    for (const [piiType, pattern] of Object.entries(patterns)) {
      const matches = args.text.match(pattern);
      if (matches) {
        found[piiType] = matches.length;
      }
    }

    return {
      has_pii: Object.keys(found).length > 0,
      pii_types: found,
      text_length: args.text.length,
    };
  },
  {
    name: 'check_pii',
    description: 'Check text for personally identifiable information (PII).',
    inputSchema: z.object({
      text: z.string().describe('The text to scan for PII'),
    }),
  },
);

const sanitizeResponse = tool(
  async (args: { text: string; piiTypes?: string }) => {
    let sanitized = args.text;
    // Mask common PII patterns
    sanitized = sanitized.replace(
      /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
      '[EMAIL REDACTED]',
    );
    sanitized = sanitized.replace(
      /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
      '[PHONE REDACTED]',
    );
    sanitized = sanitized.replace(
      /\b\d{3}-\d{2}-\d{4}\b/g,
      '[SSN REDACTED]',
    );
    sanitized = sanitized.replace(
      /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
      '[CARD REDACTED]',
    );

    return { sanitized_text: sanitized, was_modified: sanitized !== args.text };
  },
  {
    name: 'sanitize_response',
    description: 'Remove or mask PII from a response before delivering to user.',
    inputSchema: z.object({
      text: z.string().describe('The response text to sanitize'),
      piiTypes: z
        .string()
        .optional()
        .describe('Comma-separated PII types detected'),
    }),
  },
);

// -- Pipeline agents ----------------------------------------------------------

// Main assistant generates responses
export const assistant = new Agent({
  name: 'helpful_assistant',
  model: llmModel,
  instructions:
    'You are a helpful customer service assistant. Answer questions ' +
    'about account details, contact information, and general inquiries. ' +
    'When providing information, include relevant details.',
});

// Safety checker scans the response for PII
export const safetyChecker = new Agent({
  name: 'safety_checker',
  model: llmModel,
  instructions:
    "You are a safety reviewer. Check the previous agent's response " +
    'for any PII (emails, phone numbers, SSNs, credit card numbers). ' +
    'Use check_pii on the response text. If PII is found, use ' +
    'sanitize_response to clean it. Output only the sanitized version.',
  tools: [checkPii, sanitizeResponse],
});

// Pipeline: generate -> check and sanitize
const pipeline = assistant.pipe(safetyChecker);

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
    'What are the contact details for our support team? ' +
    'Include email support@company.com and phone 555-123-4567.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('44-safety-guardrails.ts') || process.argv[1]?.endsWith('44-safety-guardrails.js')) {
  main().catch(console.error);
}
