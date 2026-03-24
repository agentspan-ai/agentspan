/**
 * Vercel AI SDK -- Agent Handoff
 *
 * Demonstrates handoff from a Vercel AI SDK triage agent to a native
 * Agentspan specialist agent. The triage agent classifies the request
 * and delegates to the appropriate specialist.
 *
 * Path 1: Native triage via generateText with a classification tool.
 * Path 2: Agentspan passthrough with automatic handoff routing.
 */

import { generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { AgentRuntime, Agent } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');
const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// ── Native Agentspan specialist agents ───────────────────
const codeAgent = new Agent({
  name: 'code_specialist',
  model: MODEL,
  instructions: 'You are a coding expert. Help with programming questions concisely.',
});

const dataAgent = new Agent({
  name: 'data_specialist',
  model: MODEL,
  instructions: 'You are a data science expert. Help with data analysis questions concisely.',
});

// ── Vercel AI triage tool ────────────────────────────────
const classifyTool = tool({
  description: 'Classify a user request into a category for routing.',
  parameters: z.object({
    category: z.enum(['coding', 'data_science', 'general']).describe('The category of the request'),
    reasoning: z.string().describe('Why this category was chosen'),
  }),
  execute: async ({ category, reasoning }) => ({
    category,
    reasoning,
    handoffTo: category === 'coding' ? 'code_specialist'
             : category === 'data_science' ? 'data_specialist'
             : 'none',
  }),
});

const triageTools = { classify: classifyTool };

const queries = [
  'How do I fix a null pointer exception in Java?',
  'Help me analyze this CSV dataset for trends.',
  'What is the weather like today?',
];

const system = 'You are a triage agent. Classify the user request using the classify tool, then provide a brief response based on the classification.';

// ── Path 1: Native Vercel AI SDK triage ──────────────────
console.log('=== Native Vercel AI SDK (triage) ===');
for (const query of queries) {
  console.log(`\nQuery: ${query}`);
  const result = await generateText({
    model,
    system,
    prompt: query,
    tools: triageTools,
    maxSteps: 3,
  });
  const classifications = result.steps
    .flatMap(s => s.toolResults)
    .filter(tr => tr.toolName === 'classify');
  if (classifications.length > 0) {
    console.log('Classification:', JSON.stringify(classifications[0].result));
  }
  console.log('Response:', result.text.slice(0, 150) + (result.text.length > 150 ? '...' : ''));
  console.log('-'.repeat(60));
}

// ── Path 2: Agentspan passthrough with handoff ───────────
const triageAgent = {
  id: 'vercel_triage_agent',
  tools: triageTools,
  generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
    const result = await generateText({
      model,
      system,
      prompt: opts.prompt,
      tools: triageTools,
      maxSteps: 3,
      onStepFinish: opts.onStepFinish,
    });
    // Extract classification for metadata
    const classifications = result.steps
      .flatMap(s => s.toolResults)
      .filter(tr => tr.toolName === 'classify');
    const classification = classifications.length > 0
      ? (classifications[0].result as { category: string; handoffTo: string })
      : { category: 'general', handoffTo: 'none' };
    return {
      text: result.text,
      toolCalls: result.steps.flatMap(s => s.toolCalls),
      toolResults: result.steps.flatMap(s => s.toolResults),
      finishReason: result.finishReason,
      metadata: classification,
    };
  },
  stream: async function* () { yield { type: 'finish' as const }; },
};

console.log('\n\n=== Agentspan Passthrough (triage + handoff) ===');
const runtime = new AgentRuntime();
try {
  for (const query of queries) {
    console.log(`\nQuery: ${query}`);
    const result = await runtime.run(triageAgent, query);
    console.log('Output:', JSON.stringify(result.output).slice(0, 200));
    console.log('Status:', result.status);
    console.log('-'.repeat(60));
  }
} finally {
  await runtime.shutdown();
}
