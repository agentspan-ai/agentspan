/**
 * Google ADK Agent with Generation Config -- temperature and output control.
 *
 * Demonstrates:
 *   - Using generateContentConfig for model tuning
 *   - Low temperature for factual/deterministic responses
 *   - High temperature for creative responses
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Precise agent -- low temperature for factual responses ──────────

export const factualAgent = new LlmAgent({
  name: 'fact_checker',
  model,
  instruction:
    'You are a precise fact-checker. Provide accurate, well-sourced ' +
    'answers. Be concise and avoid speculation.',
  generateContentConfig: {
    temperature: 0.1,
  },
});

// ── Creative agent -- high temperature for creative writing ─────────

export const creativeAgent = new LlmAgent({
  name: 'storyteller',
  model,
  instruction:
    'You are an imaginative storyteller. Create vivid, engaging ' +
    'narratives with rich descriptions and unexpected twists.',
  generateContentConfig: {
    temperature: 0.9,
  },
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(factualAgent);
    await runtime.serve(factualAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // console.log('--- Factual Agent (temp=0.1) ---');
    // const factResult = await runtime.run(factualAgent, 'What is the speed of light in a vacuum?');
    // console.log('Status:', factResult.status);
    // factResult.printResult();

    // console.log('\n--- Creative Agent (temp=0.9) ---');
    // const creativeResult = await runtime.run(
    // creativeAgent,
    // 'Write a two-sentence story about a cat who discovered a hidden library.',
    // );
    // console.log('Status:', creativeResult.status);
    // creativeResult.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('05-generation-config.ts') || process.argv[1]?.endsWith('05-generation-config.js')) {
  main().catch(console.error);
}
