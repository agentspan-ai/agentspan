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

import { Agent, AgentRuntime } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

export const agent = new Agent({
  name: 'greeter',
  model: llmModel,
  instructions: 'You are a friendly assistant. Keep responses brief.',
});

export const prompt = 'Say hello and tell me a fun fact about Python.';

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
