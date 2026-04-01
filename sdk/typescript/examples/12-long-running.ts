/**
 * 12 - Long-Running Agent — fire-and-forget with status checking.
 *
 * Demonstrates starting an agent asynchronously and checking its status
 * from any process. The agent runs as a Conductor workflow and can be
 * monitored from the UI or via the API.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

export const agent = new Agent({
  name: 'saas_analyst',
  model: llmModel,
  instructions:
    'You are a data analyst. Provide a brief analysis ' +
    'when asked about data topics.',
});

// Start agent asynchronously (returns immediately)

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('12-long-running.ts') || process.argv[1]?.endsWith('12-long-running.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      'What are the key metrics to track for a SaaS product?',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
    //
    // Async handle alternative:
    // const handle = await runtime.start(
    //   agent,
    //   'What are the key metrics to track for a SaaS product?',
    // );
    // console.log(handle.executionId);
  } finally {
    await runtime.shutdown();
  }
}
