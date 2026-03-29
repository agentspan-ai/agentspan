/**
 * Basic Google ADK Agent -- simplest possible agent with instructions.
 *
 * Demonstrates:
 *   - Defining an agent using Google's Agent Development Kit (ADK)
 *   - Running via Agentspan passthrough
 *   - The runtime serializes the ADK agent and the server normalizes it
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

export const agent = new LlmAgent({
  name: 'greeter',
  model,
  instruction: 'You are a friendly assistant. Keep your responses concise and helpful.',
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // agent,
    // 'Say hello and tell me a fun fact about machine learning.',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('01-basic-agent.ts') || process.argv[1]?.endsWith('01-basic-agent.js')) {
  main().catch(console.error);
}
