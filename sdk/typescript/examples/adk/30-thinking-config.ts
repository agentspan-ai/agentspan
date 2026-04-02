/**
 * Google ADK Thinking Config -- extended reasoning for complex tasks.
 *
 * Uses ADK's generateContentConfig with thinkingConfig to enable extended
 * thinking mode, allowing the LLM to reason step-by-step before responding.
 *
 * Demonstrates:
 *   - Using thinkingConfig with thinkingBudget for extended reasoning
 *   - Tool calling combined with deep thinking
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

const calculate = new FunctionTool({
  name: 'calculate',
  description: 'Evaluate a mathematical expression.',
  parameters: z.object({
    expression: z.string().describe('A math expression to evaluate'),
  }),
  execute: async (args: { expression: string }) => {
    try {
      // Safe math evaluation using Function constructor
      const result = new Function(`return (${args.expression})`)();
      return { expression: args.expression, result };
    } catch (e) {
      return { expression: args.expression, error: String(e) };
    }
  },
});

// ── Agent with thinking config ───────────────────────────────────────

export const agent = new LlmAgent({
  name: 'deep_thinker',
  model,
  instruction:
    'You are an analytical assistant. Think carefully through complex ' +
    'problems step by step. Use the calculate tool for math.',
  tools: [calculate],
  generateContentConfig: {
    thinkingConfig: {
      thinkingBudget: 2048,
    },
  },
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'If a train travels 120 km in 2 hours, then speeds up by 50% for ' +
    'the next 3 hours, what is the total distance traveled?',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents deep_thinker
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('30-thinking-config.ts') || process.argv[1]?.endsWith('30-thinking-config.js')) {
  main().catch(console.error);
}
