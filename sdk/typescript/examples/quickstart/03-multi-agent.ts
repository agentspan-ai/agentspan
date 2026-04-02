/**
 * Multi-agent — sequential pipeline with two agents.
 */

import { Agent, AgentRuntime } from '../../src/index.js';
import { llmModel } from '../settings.js';

const researcher = new Agent({
  name: 'researcher',
  model: llmModel,
  instructions: 'Research the topic. Provide 3 key facts.',
});

const writer = new Agent({
  name: 'writer',
  model: llmModel,
  instructions: 'Write a brief summary based on the research provided.',
});

export const pipeline = researcher.pipe(writer);

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(pipeline, 'Quantum computing');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(pipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/quickstart --agents researcher
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(pipeline);
  } finally {
    await runtime.shutdown();
  }
}

export { pipeline as agent };
export const prompt = 'Quantum computing';

if (process.argv[1]?.includes('03-multi-agent')) {
  main().catch(console.error);
}
