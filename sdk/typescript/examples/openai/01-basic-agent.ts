// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * Basic OpenAI Agent -- simplest possible agent with no tools.
 *
 * Demonstrates:
 *   - Defining an agent using the real @openai/agents SDK
 *   - Running it via Agentspan passthrough (AgentRuntime)
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, setTracingDisabled } from '@openai/agents';
import { AgentRuntime } from '../../src/index.js';

// Disable OpenAI tracing for cleaner example output
setTracingDisabled(true);

export const agent = new Agent({
  name: 'greeter',
  instructions: 'You are a friendly assistant. Keep your responses concise and helpful.',
  model: 'gpt-4o-mini',
});

const prompt = 'Say hello and tell me a fun fact about the TypeScript programming language.';

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/openai --agents greeter
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('01-basic-agent.ts') || process.argv[1]?.endsWith('01-basic-agent.js')) {
  main().catch(console.error);
}
