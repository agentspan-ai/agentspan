/**
 * Google ADK Include Contents -- control context passed to sub-agents.
 *
 * When includeContents is set to "none", a sub-agent starts fresh without
 * the parent's conversation history.
 *
 * Demonstrates:
 *   - includeContents: "none" for isolated sub-agent context
 *   - includeContents: "default" (the default) for shared context
 *   - Coordinator routing to sub-agents with different context modes
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Sub-agents ───────────────────────────────────────────────────────

// Sub-agent with no parent context
export const independentSummarizer = new LlmAgent({
  name: 'independent_summarizer',
  model,
  description: 'Summarizes text without any prior conversation context.',
  instruction:
    'You are a summarizer. Summarize any text given to you concisely.',
  includeContents: 'none', // No parent context
});

// Sub-agent that sees parent context (default)
export const contextAwareHelper = new LlmAgent({
  name: 'context_aware_helper',
  model,
  description: 'A helpful assistant that builds on prior conversation context.',
  instruction:
    'You are a helpful assistant that builds on prior conversation context.',
});

// ── Coordinator ──────────────────────────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'coordinator',
  model,
  instruction:
    'You coordinate tasks. Route summarization to independent_summarizer ' +
    'and general questions to context_aware_helper.',
  subAgents: [independentSummarizer, contextAwareHelper],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(coordinator);
    await runtime.serve(coordinator);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // coordinator,
    // "Please summarize this: 'The quick brown fox jumps over the lazy dog. " +
    // 'This sentence contains every letter of the alphabet and is commonly ' +
    // "used for typography testing.'",
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('29-include-contents.ts') || process.argv[1]?.endsWith('29-include-contents.js')) {
  main().catch(console.error);
}
