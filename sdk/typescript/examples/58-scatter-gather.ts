/**
 * 58 - Scatter-Gather — massive parallel multi-agent orchestration.
 *
 * Demonstrates:
 *   - scatterGather() helper: decompose -> fan-out -> synthesize
 *   - 100 sub-agents running in parallel via FORK_JOIN_DYNAMIC
 *   - Durable execution with automatic retries on transient failures
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_SECONDARY_LLM_MODEL=openai/gpt-4o as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, scatterGather, tool } from '../src/index.js';
import { secondaryLlmModel } from './settings.js';

// -- Worker tool: simulates a knowledge base lookup --------------------------

const searchKnowledgeBase = tool(
  async (args: { query: string }) => {
    return {
      query: args.query,
      results: [
        `Key finding about ${args.query}: widely used in production systems`,
        `Community perspective on ${args.query}: growing ecosystem`,
        `Performance benchmark for ${args.query}: competitive in its niche`,
      ],
    };
  },
  {
    name: 'search_knowledge_base',
    description: 'Search the knowledge base for information on a topic.',
    inputSchema: z.object({
      query: z.string().describe('The search query'),
    }),
  },
);

// -- Worker agent: researches a single country -------------------------------

export const researcher = new Agent({
  name: 'researcher',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a country analyst. You will be given the name of a country. ' +
    'Use the search_knowledge_base tool ONCE to research that country, then ' +
    'immediately write a brief 2-3 sentence profile covering: GDP ranking, ' +
    'population, primary industries, and one unique fact. ' +
    'Do NOT call the tool more than once -- synthesize from the first result.',
  tools: [searchKnowledgeBase],
  maxTurns: 5,
});

// -- Coordinator: dispatches 100 parallel researchers ------------------------

const COUNTRIES = [
  'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola',
  'Argentina', 'Armenia', 'Australia', 'Austria', 'Azerbaijan',
  'Bahamas', 'Bahrain', 'Bangladesh', 'Barbados', 'Belarus',
  'Belgium', 'Belize', 'Benin', 'Bhutan', 'Bolivia',
  'Bosnia and Herzegovina', 'Botswana', 'Brazil', 'Brunei', 'Bulgaria',
  'Burkina Faso', 'Burundi', 'Cambodia', 'Cameroon', 'Canada',
  'Chad', 'Chile', 'China', 'Colombia', 'Congo',
  'Costa Rica', 'Croatia', 'Cuba', 'Cyprus', 'Czech Republic',
  'Denmark', 'Djibouti', 'Dominican Republic', 'Ecuador', 'Egypt',
  'El Salvador', 'Estonia', 'Ethiopia', 'Fiji', 'Finland',
  'France', 'Gabon', 'Georgia', 'Germany', 'Ghana',
  'Greece', 'Guatemala', 'Guinea', 'Haiti', 'Honduras',
  'Hungary', 'Iceland', 'India', 'Indonesia', 'Iran',
  'Iraq', 'Ireland', 'Israel', 'Italy', 'Jamaica',
  'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kuwait',
  'Laos', 'Latvia', 'Lebanon', 'Libya', 'Lithuania',
  'Luxembourg', 'Madagascar', 'Malaysia', 'Mali', 'Malta',
  'Mexico', 'Mongolia', 'Morocco', 'Mozambique', 'Myanmar',
  'Nepal', 'Netherlands', 'New Zealand', 'Nigeria', 'North Korea',
  'Norway', 'Oman', 'Pakistan', 'Panama', 'Paraguay',
];

const countryList = COUNTRIES.map((c, i) => `${i + 1}. ${c}`).join('\n');

const coordinator = scatterGather({
  name: 'coordinator',
  workers: [researcher],
  model: secondaryLlmModel,
  instructions:
    `You MUST create EXACTLY ${COUNTRIES.length} researcher calls -- one per ` +
    'country below. Each call should pass just the country name as the ' +
    'request. Issue ALL calls in a SINGLE response.\n\n' +
    `Countries:\n${countryList}\n\n` +
    `After all ${COUNTRIES.length} results return, compile a 'Global Country ` +
    'Profiles\' report organized by continent, with a brief summary table ' +
    'at the top showing the top 10 countries by GDP.',
});

// -- Run ---------------------------------------------------------------------

const prompt = `Create a comprehensive profile for each of the ${COUNTRIES.length} countries listed.`;

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('='.repeat(70));
    console.log(`  Scatter-Gather: ${COUNTRIES.length} Parallel Sub-Agents`);
    console.log('  Coordinator: openai/gpt-4o  |  Workers: anthropic/claude-sonnet');
    console.log('='.repeat(70));
    console.log(`\nPrompt: ${prompt}`);
    console.log(`Countries: ${COUNTRIES.length}`);
    console.log(`Dispatching ${COUNTRIES.length} parallel researcher agents...\n`);
    const result = await runtime.run(coordinator, prompt);
    console.log('--- Coordinator Result ---');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(coordinator);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents coordinator
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(coordinator);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('58-scatter-gather.ts') || process.argv[1]?.endsWith('58-scatter-gather.js')) {
  main().catch(console.error);
}
