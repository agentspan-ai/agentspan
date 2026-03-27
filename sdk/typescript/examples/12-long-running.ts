/**
 * 12 - Long-Running Agent — fire-and-forget with status checking.
 *
 * Demonstrates starting an agent asynchronously and checking its status
 * from any process. The agent runs as a Conductor workflow and can be
 * monitored from the UI or via the API.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
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
    const handle = await runtime.start(
      agent,
      'What are the key metrics to track for a SaaS product?',
    );
    console.log(`Agent started: ${handle.workflowId}`);

    // Poll for completion
    let completed = false;
    for (let i = 0; i < 30; i++) {
      const status = await handle.getStatus();
      console.log(`  [${i}s] Status: ${status.status} | Complete: ${status.isComplete}`);
      if (status.isComplete) {
        console.log(`\nResult: ${JSON.stringify(status.output)}`);
        completed = true;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    if (!completed) {
      console.log('\nAgent still running. Check the Conductor UI:');
      console.log(`  http://localhost:8080/execution/${handle.workflowId}`);
    }
  } finally {
    await runtime.shutdown();
  }
}
