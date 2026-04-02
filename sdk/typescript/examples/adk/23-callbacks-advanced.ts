/**
 * Google ADK Callbacks -- lifecycle hooks on agent execution.
 *
 * Demonstrates:
 *   - beforeModelCallback: runs before each LLM call (can log or modify)
 *   - afterModelCallback: runs after each LLM call (can inspect or modify)
 *   - Callbacks are registered as Conductor worker tasks (same as tools)
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent } from '@google/adk';
import type { BeforeModelCallback, AfterModelCallback } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Callback functions ────────────────────────────────────────────
// These run before/after each LLM invocation.
// Return undefined to continue normally; return an LlmResponse to short-circuit.

const logBeforeModel: BeforeModelCallback = ({ context, request }) => {
  const agentName = context.agentName;
  console.log(`[CALLBACK] Before model call for agent '${agentName}'`);
  // Return undefined to continue normally (don't skip the LLM call)
  return undefined;
};

const inspectAfterModel: AfterModelCallback = ({ context, response }) => {
  const agentName = context.agentName;
  const text = response?.content?.parts
    ?.map((p: { text?: string }) => p.text ?? '')
    .join('') ?? '';
  const wordCount = text.split(/\s+/).filter(Boolean).length;
  console.log(`[CALLBACK] After model call for '${agentName}': ${wordCount} words generated`);

  // Flag if response is too long
  if (wordCount > 500) {
    console.log(`[CALLBACK] Warning: Response exceeds 500 words (${wordCount})`);
  }

  // Return undefined to keep the original response
  return undefined;
};

// ── Agent with callbacks ──────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'monitored_assistant',
  model,
  instruction:
    'You are a helpful assistant. Answer questions concisely. ' +
    'Keep responses under 200 words.',
  beforeModelCallback: logBeforeModel,
  afterModelCallback: inspectAfterModel,
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Explain the difference between supervised and unsupervised machine learning.',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents monitored_assistant
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('23-callbacks-advanced.ts') || process.argv[1]?.endsWith('23-callbacks-advanced.js')) {
  main().catch(console.error);
}
