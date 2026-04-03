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
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
