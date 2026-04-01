/**
 * 63e - Run Monitoring Agent — use runtime.run() and print the result.
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { monitoringAgent } from './63d-serve-from-package.js';
import { AgentRuntime } from '../src/index.js';

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('63e-run-monitoring.ts') || process.argv[1]?.endsWith('63e-run-monitoring.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(monitoringAgent, 'Is everything healthy? Run a full check.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(monitoringAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(monitoringAgent);
  } finally {
    await runtime.shutdown();
  }
}
