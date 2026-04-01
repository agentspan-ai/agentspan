/**
 * Parallel Agents — fan-out / fan-in.
 *
 * Demonstrates the parallel strategy where all sub-agents run concurrently
 * on the same input and their results are aggregated.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

// -- Specialist analysts -----------------------------------------------------

export const marketAnalyst = new Agent({
  name: 'market_analyst',
  model: llmModel,
  instructions:
    'You are a market analyst. Analyze the given topic from a market perspective: ' +
    'market size, growth trends, key players, and opportunities.',
});

export const riskAnalyst = new Agent({
  name: 'risk_analyst',
  model: llmModel,
  instructions:
    'You are a risk analyst. Analyze the given topic for risks: ' +
    'regulatory risks, technical risks, competitive threats, and mitigation strategies.',
});

export const complianceChecker = new Agent({
  name: 'compliance',
  model: llmModel,
  instructions:
    'You are a compliance specialist. Check the given topic for compliance considerations: ' +
    'data privacy, regulatory requirements, and industry standards.',
});

// -- Parallel analysis -------------------------------------------------------

export const analysis = new Agent({
  name: 'analysis',
  model: llmModel,
  agents: [marketAnalyst, riskAnalyst, complianceChecker],
  strategy: 'parallel',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(analysis);
    // await runtime.serve(analysis);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    analysis,
    'Launching an AI-powered healthcare diagnostic tool in the US market',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('07-parallel-agents.ts') || process.argv[1]?.endsWith('07-parallel-agents.js')) {
  main().catch(console.error);
}
