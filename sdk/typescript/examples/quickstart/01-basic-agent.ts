/**
 * Basic agent — the simplest possible agentspan example.
 */

import { Agent, AgentRuntime } from '../../src/index.js';
import { llmModel } from '../settings.js';

export const agent = new Agent({
  name: 'greeter',
  model: llmModel,
  instructions: 'You are a friendly assistant. Keep responses brief.',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Hello! What can you do?');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

export const prompt = 'Hello! What can you do?';

if (process.argv[1]?.includes('01-basic-agent')) {
  main().catch(console.error);
}
