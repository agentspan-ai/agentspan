/**
 * 48 - Planner — agent that plans before executing.
 *
 * When `planner: true`, the server enhances the system prompt with planning
 * instructions so the agent creates a step-by-step plan before executing
 * tools.
 *
 * Requirements:
 *   - Conductor server with planner support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tools -------------------------------------------------------------------

const searchWeb = tool(
  async (args: { query: string }) => {
    const results: Record<string, string[]> = {
      'climate change': [
        'Solar energy costs dropped 89% since 2010',
        'Wind power is cheapest in many regions',
      ],
      'renewable energy': [
        'Renewables = 30% of global electricity (2023)',
        'Solar capacity grew 50% year-over-year',
      ],
    };
    for (const [key, vals] of Object.entries(results)) {
      if (key.split(' ').some((word) => args.query.toLowerCase().includes(word))) {
        return { query: args.query, results: vals };
      }
    }
    return { query: args.query, results: ['No specific results.'] };
  },
  {
    name: 'search_web',
    description: 'Search the web for information.',
    inputSchema: z.object({
      query: z.string().describe('Search query string'),
    }),
  },
);

const writeSection = tool(
  async (args: { title: string; content: string }) => {
    return { section: `## ${args.title}\n\n${args.content}` };
  },
  {
    name: 'write_section',
    description: 'Write a section of a report.',
    inputSchema: z.object({
      title: z.string().describe('Section title'),
      content: z.string().describe('Section body text'),
    }),
  },
);

// -- Agent -------------------------------------------------------------------

export const agent = new Agent({
  name: 'research_writer_48',
  model: llmModel,
  instructions:
    'You are a research writer. Research topics thoroughly and ' +
    'write structured reports with multiple sections.',
  tools: [searchWeb, writeSection],
  planner: true,
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    agent,
    'Write a brief report on renewable energy and climate change solutions.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('48-planner.ts') || process.argv[1]?.endsWith('48-planner.js')) {
  main().catch(console.error);
}
