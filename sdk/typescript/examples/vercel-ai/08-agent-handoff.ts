/**
 * Vercel AI SDK Tools + Native Agent -- Agent Handoff
 *
 * Demonstrates multi-agent orchestration with handoff strategy using AI SDK tools.
 * A triage agent classifies requests and hands off to specialist agents,
 * each equipped with their own AI SDK tools.
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import { Agent, AgentRuntime } from '../../src/index.js';

// ── Specialist tools (Vercel AI SDK format) ──────────────

const lookupCode = aiTool({
  description: 'Look up a code snippet or programming concept.',
  parameters: z.object({
    topic: z.string().describe('Programming topic to look up'),
  }),
  execute: async ({ topic }) => ({
    topic,
    answer: `Here is the solution for "${topic}": Use try-catch with specific exception types for robust error handling.`,
  }),
});

const analyzeData = aiTool({
  description: 'Analyze a dataset description and return insights.',
  parameters: z.object({
    dataset: z.string().describe('Description of the dataset'),
  }),
  execute: async ({ dataset }) => ({
    dataset,
    insights: `Dataset "${dataset}" shows positive correlation. Recommend further statistical testing.`,
  }),
});

// ── Specialist agents ────────────────────────────────────

const codeSpecialist = new Agent({
  name: 'code_specialist',
  model: 'openai/gpt-4o-mini',
  instructions:
    'You are a coding expert. Use the lookupCode tool to help users with programming questions.',
  tools: [lookupCode],
});

const dataSpecialist = new Agent({
  name: 'data_specialist',
  model: 'openai/gpt-4o-mini',
  instructions:
    'You are a data science expert. Use the analyzeData tool to help users with data analysis.',
  tools: [analyzeData],
});

// ── Triage agent with handoff strategy ───────────────────

const triageAgent = new Agent({
  name: 'triage_agent',
  model: 'openai/gpt-4o-mini',
  instructions:
    "You are a triage agent. Determine the user's need and hand off:\n" +
    '- Coding questions -> code_specialist\n' +
    '- Data analysis questions -> data_specialist\n' +
    'Be brief in your initial response before handing off.',
  agents: [codeSpecialist, dataSpecialist],
  strategy: 'handoff',
});

// ── Test queries ─────────────────────────────────────────
const queries = [
  'How do I fix a null pointer exception in Java?',
  'Help me analyze this CSV dataset for trends.',
  'What is the weather like today?',
];

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    for (const query of queries) {
      console.log(`\nQuery: ${query}`);
      const result = await runtime.run(triageAgent, query);
      console.log('Status:', result.status);
      result.printResult();
      console.log('-'.repeat(60));
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
