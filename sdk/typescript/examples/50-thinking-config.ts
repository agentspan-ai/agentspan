/**
 * 50 - Thinking Config — enable extended reasoning for complex tasks.
 *
 * When `thinkingBudgetTokens` is set, the agent uses extended thinking
 * mode, allowing the LLM to reason step-by-step before responding.
 *
 * Requirements:
 *   - Conductor server with thinking config support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tool --------------------------------------------------------------------

const calculate = tool(
  async (args: { expression: string }) => {
    try {
      const fn = new Function(`return (${args.expression});`);
      return { expression: args.expression, result: fn() };
    } catch (e) {
      return { expression: args.expression, error: String(e) };
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a mathematical expression.',
    inputSchema: z.object({
      expression: z.string().describe("A math expression to evaluate (e.g., '2 + 3 * 4')"),
    }),
  },
);

// -- Agent -------------------------------------------------------------------

export const agent = new Agent({
  name: 'deep_thinker_50',
  model: llmModel,
  instructions:
    'You are an analytical assistant. Think carefully through complex ' +
    'problems step by step. Use the calculate tool for math.',
  tools: [calculate],
  thinkingBudgetTokens: 2048,
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
    'If a train travels 120 km in 2 hours, then speeds up by 50% for ' +
    'the next 3 hours, what is the total distance traveled?',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('50-thinking-config.ts') || process.argv[1]?.endsWith('50-thinking-config.js')) {
  main().catch(console.error);
}
