/**
 * Parallel Agent -- ParallelAgent runs sub-agents concurrently.
 *
 * Demonstrates:
 *   - ParallelAgent from @google/adk for concurrent execution
 *   - All sub-agents run in parallel and their results are aggregated
 *   - Three analysts providing different perspectives simultaneously
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, ParallelAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// Three analysts run in parallel
export const marketAnalyst = new LlmAgent({
  name: 'market_analyst',
  model,
  description: 'Analyzes market trends.',
  instruction:
    'You are a market analyst. Given the company or product topic, ' +
    'provide a brief 2-3 sentence market analysis. Focus on trends and competition.',
});

export const techAnalyst = new LlmAgent({
  name: 'tech_analyst',
  model,
  description: 'Evaluates technology aspects.',
  instruction:
    'You are a technology analyst. Given the company or product topic, ' +
    'provide a brief 2-3 sentence technical evaluation. Focus on innovation and capabilities.',
});

export const riskAnalyst = new LlmAgent({
  name: 'risk_analyst',
  model,
  description: 'Assesses risks.',
  instruction:
    'You are a risk analyst. Given the company or product topic, ' +
    'provide a brief 2-3 sentence risk assessment. Focus on potential challenges.',
});

// All three run in parallel
export const parallelAnalysis = new ParallelAgent({
  name: 'parallel_analysis',
  subAgents: [marketAnalyst, techAnalyst, riskAnalyst],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    parallelAnalysis,
    "Analyze Tesla's electric vehicle business",
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(parallelAnalysis);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents parallel_analysis
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(parallelAnalysis);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('12-parallel-agent.ts') || process.argv[1]?.endsWith('12-parallel-agent.js')) {
  main().catch(console.error);
}
