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

import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

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
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query string' },
      },
      required: ['query'],
    },
  },
);

const writeSection = tool(
  async (args: { title: string; content: string }) => {
    return { section: `## ${args.title}\n\n${args.content}` };
  },
  {
    name: 'write_section',
    description: 'Write a section of a report.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Section title' },
        content: { type: 'string', description: 'Section body text' },
      },
      required: ['title', 'content'],
    },
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

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Write a brief report on renewable energy and climate change solutions.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents research_writer_48
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
