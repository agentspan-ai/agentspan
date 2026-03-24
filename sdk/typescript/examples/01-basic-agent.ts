/**
 * 01 - Basic Agent
 *
 * Demonstrates the simplest possible agent: a single LLM agent
 * with model + instructions, run via runtime.run().
 */

import { Agent, AgentRuntime } from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Define a simple agent --
const assistant = new Agent({
  name: 'helpful_assistant',
  model: MODEL,
  instructions: 'You are a helpful assistant. Answer concisely.',
  maxTurns: 5,
  temperature: 0.7,
});

// -- Run it --
async function main() {
  const runtime = new AgentRuntime();

  const result = await runtime.run(assistant, 'What is the capital of France?');
  result.printResult();

  // Access individual fields
  console.log('Status:', result.status);
  console.log('Output:', result.output);
  console.log('Success:', result.isSuccess);

  await runtime.shutdown();
}

main().catch(console.error);
