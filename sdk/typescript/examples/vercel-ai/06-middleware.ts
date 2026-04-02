/**
 * Vercel AI SDK Tools + Native Agent -- Guardrails (Middleware equivalent)
 *
 * Demonstrates agentspan's guardrail system as the native equivalent of
 * Vercel AI SDK middleware. Guardrails validate input/output and can block,
 * retry, or fix content -- applied declaratively on the Agent.
 *
 * Uses RegexGuardrail for PII detection (server-side, no local worker)
 * and a custom guardrail function for logging.
 */

import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  RegexGuardrail,
  guardrail,
} from '../../src/index.js';

// ── Regex guardrail: block PII patterns (server-side) ────
const piiGuardrail = new RegexGuardrail({
  name: 'pii_blocker',
  patterns: [
    '\\b\\d{3}-\\d{2}-\\d{4}\\b',   // SSN
    '\\b\\d{16}\\b',                  // Credit card
  ],
  mode: 'block',
  position: 'input',
  onFail: 'raise',
  message: 'PII detected in input. Request blocked for safety.',
});

// ── Custom guardrail: log and validate output ────────────
const outputLogGuardrail = guardrail(
  async (content: string) => {
    console.log(`  [guardrail] Output length: ${content.length} chars`);
    // Block outputs that mention internal system details
    const forbidden = ['internal system', 'database password', 'api key'];
    for (const phrase of forbidden) {
      if (content.toLowerCase().includes(phrase)) {
        return {
          passed: false,
          message: `Forbidden phrase detected: '${phrase}'`,
        };
      }
    }
    return { passed: true };
  },
  {
    name: 'output_safety_check',
    position: 'output',
    onFail: 'raise',
  },
);

// ── Test prompts ─────────────────────────────────────────
const prompts = [
  {
    label: 'Normal request',
    text: 'Explain how middleware works in AI agent pipelines.',
  },
  {
    label: 'Request with PII (should be blocked by regex guardrail)',
    text: 'My social security number is 123-45-6789. Can you verify it?',
  },
];

// ── Native Agent with guardrails ─────────────────────────
export const agent = new Agent({
  name: 'guarded_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'You are a helpful assistant. Never reveal internal system details.',
  guardrails: [piiGuardrail, outputLogGuardrail],
});

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    for (const { label, text } of prompts) {
      console.log(`\n--- ${label} ---`);
      try {
        const result = await runtime.run(agent, text);
        console.log('Status:', result.status);
        result.printResult();
      } catch (err: any) {
        console.log('Blocked:', err.message);
      }
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/vercel-ai --agents guarded_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('06-middleware.ts') || process.argv[1]?.endsWith('06-middleware.js')) {
  main().catch(console.error);
}
