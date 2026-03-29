/**
 * Google ADK Agent with Planning -- thinking config for step-by-step reasoning.
 *
 * Demonstrates:
 *   - Using generateContentConfig with thinkingConfig to add a planning phase
 *   - The agent reasons step-by-step before executing
 *   - Tools for research and structured output
 *
 * Note: The Python ADK uses BuiltInPlanner, which is not yet available in the
 * TypeScript ADK. We achieve similar behavior via generateContentConfig's
 * thinkingConfig, which enables extended thinking/planning.
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const searchWeb = new FunctionTool({
  name: 'search_web',
  description: 'Search the web for information.',
  parameters: z.object({
    query: z.string().describe('Search query string'),
  }),
  execute: async (args: { query: string }) => {
    const results: Record<string, { results: string[] }> = {
      'climate change solutions': {
        results: [
          'Solar energy costs dropped 89% since 2010',
          'Wind power is now cheapest energy source in many regions',
          'Carbon capture technology advancing rapidly',
        ],
      },
      'renewable energy statistics': {
        results: [
          'Renewables account for 30% of global electricity (2023)',
          'Solar capacity grew 50% year-over-year',
          'China leads in renewable energy investment',
        ],
      },
    };
    const queryLower = args.query.toLowerCase();
    for (const [key, val] of Object.entries(results)) {
      if (key.split(' ').some((word) => queryLower.includes(word))) {
        return { query: args.query, ...val };
      }
    }
    return { query: args.query, results: ['No specific results found.'] };
  },
});

const writeSection = new FunctionTool({
  name: 'write_section',
  description: 'Write a section of a report.',
  parameters: z.object({
    title: z.string().describe('Section title'),
    content: z.string().describe('Section body text'),
  }),
  execute: async (args: { title: string; content: string }) => {
    return { section: `## ${args.title}\n\n${args.content}` };
  },
});

// ── Agent with planner (via thinkingConfig) ──────────────────────────

export const agent = new LlmAgent({
  name: 'research_writer',
  model,
  instruction:
    'You are a research writer. When given a topic, research it ' +
    'thoroughly and write a structured report with multiple sections. ' +
    'Think step by step: first plan your research, then search for data, ' +
    'then write each section.',
  tools: [searchWeb, writeSection],
  generateContentConfig: {
    thinkingConfig: {
      thinkingBudget: 1024,
    },
  },
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // agent,
    // 'Write a brief report on the current state of renewable energy ' +
    // 'and climate change solutions.',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('24-planner.ts') || process.argv[1]?.endsWith('24-planner.js')) {
  main().catch(console.error);
}
