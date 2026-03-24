/**
 * Vercel AI SDK -- Agent Handoff
 *
 * Demonstrates handoff from a Vercel AI SDK agent to a native Agentspan
 * agent. The triage agent classifies the request and delegates to
 * the appropriate specialist.
 *
 * In production you would use:
 *   import { generateText } from 'ai';
 *   // Vercel AI triage agent
 *   // Agentspan native specialist agents
 */

import { AgentRuntime, Agent } from '../../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Native Agentspan specialist agents --
const codeAgent = new Agent({
  name: 'code_specialist',
  model: MODEL,
  instructions: 'You are a coding expert. Help with programming questions concisely.',
});

const dataAgent = new Agent({
  name: 'data_specialist',
  model: MODEL,
  instructions: 'You are a data science expert. Help with data analysis questions.',
});

// -- Mock Vercel AI SDK triage agent --
// Detection requires: .generate() + .stream() + .tools
const triageAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    const prompt = options.prompt.toLowerCase();
    let category: string;
    let handoffTo: string;

    if (prompt.includes('code') || prompt.includes('program') || prompt.includes('function') || prompt.includes('bug')) {
      category = 'coding';
      handoffTo = 'code_specialist';
    } else if (prompt.includes('data') || prompt.includes('csv') || prompt.includes('analysis') || prompt.includes('statistics')) {
      category = 'data_science';
      handoffTo = 'data_specialist';
    } else {
      category = 'general';
      handoffTo = 'none';
    }

    return {
      text:
        `[Triage] Classified as: ${category}\n` +
        `[Triage] ${handoffTo !== 'none' ? `Handing off to ${handoffTo}` : 'Handling directly'}\n\n` +
        (handoffTo === 'none'
          ? 'I can help you with that general question directly.'
          : `Routing to ${handoffTo} for specialized assistance.`),
      toolCalls: [],
      finishReason: 'stop' as const,
      metadata: { category, handoffTo },
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  id: 'vercel_triage_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  const queries = [
    'How do I fix a null pointer exception in Java?',
    'Help me analyze this CSV dataset for trends.',
    'What is the weather like today?',
  ];

  for (const query of queries) {
    console.log(`\nQuery: ${query}`);
    const result = await runtime.run(triageAgent, query);
    console.log('Status:', result.status);
    result.printResult();
    console.log('-'.repeat(60));
  }

  await runtime.shutdown();
}

main().catch(console.error);
