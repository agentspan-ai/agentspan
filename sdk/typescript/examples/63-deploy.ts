/**
 * 63 - Deploy — register agents on the server (CI/CD step).
 *
 * deploy() sends agent configs to the server, which compiles them into
 * Conductor workflow definitions. No local workers are started.
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tools -------------------------------------------------------------------

const searchDocs = tool(
  async (args: { query: string }) => {
    return `Found 3 results for: ${args.query}`;
  },
  {
    name: 'search_docs',
    description: 'Search internal documentation.',
    inputSchema: z.object({
      query: z.string().describe('Search query string'),
    }),
  },
);

const checkStatus = tool(
  async (args: { service: string }) => {
    return `${args.service}: healthy`;
  },
  {
    name: 'check_status',
    description: 'Check service health status.',
    inputSchema: z.object({
      service: z.string().describe('Name of the service to check'),
    }),
  },
);

// -- Define agents -----------------------------------------------------------

export const docAssistant = new Agent({
  name: 'doc_assistant',
  model: llmModel,
  tools: [searchDocs],
  instructions: 'Help users find documentation. Use search_docs to look up answers.',
});

export const opsBot = new Agent({
  name: 'ops_bot',
  model: llmModel,
  tools: [checkStatus],
  instructions: 'Monitor service health. Use check_status to inspect services.',
});

// -- Deploy: compile + register on server ------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('63-deploy.ts') || process.argv[1]?.endsWith('63-deploy.js')) {
  const runtime = new AgentRuntime();
  try {
    const agents = [docAssistant, opsBot];
    for (const a of agents) {
      const info = await runtime.deploy(a);
      console.log(`Deployed: ${info.agentName} -> ${info.workflowName}`);
    }

    console.log(`\n${agents.length} agent(s) registered on server.`);
    console.log('Now run 63b-serve.ts to start workers, then 63c-run-by-name.ts to execute.');
  } finally {
    await runtime.shutdown();
  }
}
