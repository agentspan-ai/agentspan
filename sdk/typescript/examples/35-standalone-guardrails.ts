/**
 * 35 - Standalone Guardrails
 *
 * The guardrail() function produces a GuardrailDef with an attached func.
 * You can call the func directly to validate any text in-process, no server
 * needed.
 *
 * This example demonstrates:
 *   Part 1: Standalone -- call guardrails directly, no server needed.
 *   Part 2: As Conductor workers -- register guardrails as worker tasks
 *           (referenced by name from any agent).
 *
 * Requirements:
 *   Part 1 (standalone): none -- no server, no LLM, no workers.
 *   Part 2 (as workers): Conductor server
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { guardrail } from '../src/index.js';
import type { GuardrailResult, GuardrailDef } from '../src/index.js';

// -- Define guardrails -------------------------------------------------------

export const noPii = guardrail(
  (content: string): GuardrailResult => {
    const ccPattern = /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/;
    const ssnPattern = /\b\d{3}-\d{2}-\d{4}\b/;

    if (ccPattern.test(content) || ssnPattern.test(content)) {
      return {
        passed: false,
        message: 'Contains PII (credit card or SSN).',
      };
    }
    return { passed: true };
  },
  { name: 'no_pii' },
);

export const noProfanity = guardrail(
  (content: string): GuardrailResult => {
    const banned = new Set(['damn', 'hell', 'crap']);
    const words = new Set(content.toLowerCase().split(/\s+/));
    const found = [...words].filter((w) => banned.has(w));
    if (found.length > 0) {
      return {
        passed: false,
        message: `Profanity detected: ${found.sort().join(', ')}`,
      };
    }
    return { passed: true };
  },
  { name: 'no_profanity' },
);

export const wordLimit = guardrail(
  (content: string): GuardrailResult => {
    const count = content.split(/\s+/).filter(Boolean).length;
    if (count > 100) {
      return {
        passed: false,
        message: `Too long (${count} words). Limit is 100.`,
      };
    }
    return { passed: true };
  },
  { name: 'word_limit' },
);

// ============================================================================
// Part 1: Standalone -- call guardrails directly, no server needed
// ============================================================================

function validate(text: string, guardrails: GuardrailDef[]): boolean {
  let allPassed = true;
  for (const g of guardrails) {
    if (!g.func) continue;
    const result = g.func(text) as GuardrailResult;
    if (result.passed) {
      console.log(`  [PASS] ${g.name}`);
    } else {
      console.log(`  [FAIL] ${g.name}: ${result.message}`);
      allPassed = false;
    }
  }
  return allPassed;
}

function runStandalone(): void {
  console.log('='.repeat(60));
  console.log('Part 1: Standalone guardrails (no server)');
  console.log('='.repeat(60));

  const checks = [noPii, noProfanity, wordLimit];

  console.log('\nTest 1 -- clean text:');
  const text1 = 'Hello, your order #1234 has shipped and will arrive Friday.';
  let passed = validate(text1, checks);
  console.log(`  Result: ${passed ? 'PASSED' : 'BLOCKED'}\n`);

  console.log('Test 2 -- contains credit card number:');
  const text2 = 'Your card on file is 4532-0150-1234-5678. Order confirmed.';
  passed = validate(text2, checks);
  console.log(`  Result: ${passed ? 'PASSED' : 'BLOCKED'}\n`);

  console.log('Test 3 -- contains profanity:');
  const text3 = 'What the hell happened to my order?';
  passed = validate(text3, checks);
  console.log(`  Result: ${passed ? 'PASSED' : 'BLOCKED'}\n`);

  console.log('Test 4 -- exceeds word limit:');
  const text4 = 'word '.repeat(150);
  passed = validate(text4, checks);
  console.log(`  Result: ${passed ? 'PASSED' : 'BLOCKED'}\n`);
}

// ============================================================================

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('35-standalone-guardrails.ts') || process.argv[1]?.endsWith('35-standalone-guardrails.js')) {
  runStandalone();

  console.log('-'.repeat(60));
  console.log('To run guardrails as Conductor workers (no agent needed):');
  console.log('  npx tsx examples/35-standalone-guardrails.ts --workers');
}
