/**
 * Google ADK Nested Strategies -- ParallelAgent inside SequentialAgent.
 *
 * Demonstrates composing agent strategies: parallel research runs
 * concurrently, then results flow into a sequential summarizer.
 *
 * Architecture:
 *   analysis_pipeline (SequentialAgent)
 *     sub_agents:
 *       1. research_phase (ParallelAgent)
 *          - market_analyst
 *          - risk_analyst
 *       2. summarizer
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, ParallelAgent, SequentialAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Parallel research agents ─────────────────────────────────────────

export const marketAnalyst = new LlmAgent({
  name: 'market_analyst',
  model,
  instruction:
    'You are a market analyst. Analyze the market size, growth rate, ' +
    'and key players for the given topic. Be concise (3-4 bullet points).',
});

export const riskAnalyst = new LlmAgent({
  name: 'risk_analyst',
  model,
  instruction:
    'You are a risk analyst. Identify the top 3 risks: regulatory, ' +
    'technical, and competitive. Be concise.',
});

// Both run concurrently
export const parallelResearch = new ParallelAgent({
  name: 'research_phase',
  subAgents: [marketAnalyst, riskAnalyst],
});

// ── Summarizer ───────────────────────────────────────────────────────

export const summarizer = new LlmAgent({
  name: 'summarizer',
  model,
  instruction:
    'You are an executive briefing writer. Synthesize the market analysis ' +
    'and risk assessment into a concise executive summary (1 paragraph).',
});

// ── Pipeline: parallel -> sequential ─────────────────────────────────

export const pipeline = new SequentialAgent({
  name: 'analysis_pipeline',
  subAgents: [parallelResearch, summarizer],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    pipeline,
    'Launching an AI-powered healthcare diagnostics tool in the US',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(pipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents analysis_pipeline
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(pipeline);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('32-nested-strategies.ts') || process.argv[1]?.endsWith('32-nested-strategies.js')) {
  main().catch(console.error);
}
