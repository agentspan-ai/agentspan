/**
 * 63d - Serve from Package — auto-discover and serve all agents.
 *
 * Demonstrates:
 *   - discoverAgents() for auto-discovery of agents
 *   - Mixing explicit agents with package-based discovery
 *
 * NOTE: serve() is blocking. This example prints usage instructions.
 * In production, uncomment the runtime.serve() call.
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Explicit agent ----------------------------------------------------------

const healthCheck = tool(
  async () => {
    return 'All systems operational';
  },
  {
    name: 'health_check',
    description: 'Perform a basic health check.',
    inputSchema: z.object({}),
  },
);

export const monitoringAgent = new Agent({
  name: 'monitoring',
  model: llmModel,
  tools: [healthCheck],
  instructions: 'You monitor system health.',
});

// -- Serve -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('63d-serve-from-package.ts') || process.argv[1]?.endsWith('63d-serve-from-package.js')) {
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
