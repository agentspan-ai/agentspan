/**
 * Basic Agent — 5-line hello world.
 *
 * Demonstrates the simplest possible agent: define an agent, call
 * `runtime.run()`, and print the result.
 *
 * Requirements:
 *   - Agentspan server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL set as environment variable (optional)
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

export const agent = new Agent({
  name: 'greeter',
  model: llmModel,
  instructions: 'You are a friendly assistant. Keep responses brief.',
});

export const prompt = 'Say hello and tell me a fun fact about Python.';

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents greeter
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('01-basic-agent.ts') || process.argv[1]?.endsWith('01-basic-agent.js')) {
  main().catch(console.error);
}
