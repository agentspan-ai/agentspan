/**
 * 63b - Serve — keep tool workers running as a persistent service.
 *
 * serve() registers the tool functions as Conductor workers and starts
 * polling for tasks. The workflow must already exist on the server
 * (from a prior deploy() or run() call).
 *
 * NOTE: serve() is blocking. This example defines the agents and
 * prints a message about how to call serve(). In production, uncomment
 * the runtime.serve() call and run this as a long-lived process.
 *
 * Requirements:
 *   - Conductor server running
 *   - Agents already deployed (run 63-deploy.ts first)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tools (same definitions as 63-deploy.ts) --------------------------------

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

// -- Serve: register workers and block ---------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('63b-serve.ts') || process.argv[1]?.endsWith('63b-serve.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(opsBot, 'Check the status of the API gateway.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(docAssistant);
    // await runtime.deploy(opsBot);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(docAssistant, opsBot);
  } finally {
    await runtime.shutdown();
  }
}
