/**
 * 04 - Guardrails
 *
 * Demonstrates three guardrail types:
 * - RegexGuardrail: pattern matching (PII blocker)
 * - LLMGuardrail: LLM-based validation (bias detector)
 * - Custom guardrail function
 */

import {
  Agent,
  AgentRuntime,
  RegexGuardrail,
  LLMGuardrail,
  guardrail,
} from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- RegexGuardrail: block PII patterns --
const piiBlocker = new RegexGuardrail({
  name: 'pii_blocker',
  patterns: [
    '\\b\\d{3}-\\d{2}-\\d{4}\\b',       // SSN
    '\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b', // Credit card
  ],
  mode: 'block',
  position: 'output',
  onFail: 'retry',
  message: 'PII detected. Please redact personal information.',
});

// -- LLMGuardrail: detect biased language --
const biasDetector = new LLMGuardrail({
  name: 'bias_detector',
  model: 'openai/gpt-4o-mini',
  policy: 'Check for biased language or stereotypes. If found, provide a corrected version.',
  position: 'output',
  onFail: 'fix',
  maxTokens: 5000,
});

// -- Custom guardrail function --
const factChecker = guardrail(
  (content: string): GuardrailResult => {
    const redFlags = ['the best', 'always', 'never', 'guaranteed'];
    const found = redFlags.filter((f) =>
      content.toLowerCase().includes(f),
    );
    if (found.length > 0) {
      return { passed: false, message: `Unverifiable claims: ${found.join(', ')}` };
    }
    return { passed: true };
  },
  {
    name: 'fact_checker',
    position: 'output',
    onFail: 'human',
  },
);

// -- Agent with all guardrails --
export const safeWriter = new Agent({
  name: 'safe_writer',
  model: MODEL,
  instructions: 'Write informative content. Avoid PII and biased language.',
  guardrails: [
    piiBlocker.toGuardrailDef(),
    biasDetector.toGuardrailDef(),
    factChecker,
  ],
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(safeWriter);
    // await runtime.serve(safeWriter);
    // Direct run for local development:
    const result = await runtime.run(safeWriter, 'Write about AI safety best practices.');
    result.printResult();
    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('04-guardrails.ts') || process.argv[1]?.endsWith('04-guardrails.js')) {

  main().catch(console.error);
}
