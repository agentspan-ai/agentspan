/**
 * Token & Cost Tracking -- monitor LLM token usage per agent run.
 *
 * Demonstrates the `tokenUsage` field on `AgentResult` which provides
 * aggregated token usage across all LLM calls in an agent execution.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

const calculate = tool(
  async (args: { expression: string }) => {
    // For demo only -- use a safe evaluator in production
    const result = new Function('return ' + args.expression)();
    return String(result);
  },
  {
    name: 'calculate',
    description: 'Evaluate a mathematical expression.',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'The mathematical expression to evaluate' },
      },
      required: ['expression'],
    },
  },
);

export const agent = new Agent({
  name: 'math_tutor',
  model: llmModel,
  tools: [calculate],
  instructions:
    'You are a math tutor. Solve problems step by step, using the calculate ' +
    'tool for computations. Explain each step clearly.',
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Calculate the compound interest on $10,000 at 5% annual rate ' +
    'compounded monthly for 3 years.',
    );
    result.printResult();

    // Token usage is automatically extracted from the workflow
    if (result.tokenUsage) {
    console.log('Token Usage Summary:');
    console.log(`  Prompt tokens:     ${result.tokenUsage.promptTokens}`);
    console.log(`  Completion tokens: ${result.tokenUsage.completionTokens}`);
    console.log(`  Total tokens:      ${result.tokenUsage.totalTokens}`);

    // Estimate cost (example pricing -- adjust for your model)
    const promptCost = result.tokenUsage.promptTokens * 0.0025 / 1000;
    const completionCost = result.tokenUsage.completionTokens * 0.01 / 1000;
    console.log(`\n  Estimated cost: $${(promptCost + completionCost).toFixed(4)}`);
    } else {
    console.log('(Token usage not available from workflow)');
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents math_tutor
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('23-token-tracking.ts') || process.argv[1]?.endsWith('23-token-tracking.js')) {
  main().catch(console.error);
}
