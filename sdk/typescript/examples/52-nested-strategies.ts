/**
 * 52 - Nested Strategies — parallel agents inside a sequential pipeline.
 *
 * Demonstrates composing strategies: a parallel phase runs multiple
 * research agents concurrently, followed by a sequential summarizer.
 *
 *   pipeline = parallelResearch >> summarizer
 *
 * Requirements:
 *   - Conductor server
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

// -- Parallel research phase -------------------------------------------------

export const marketAnalyst = new Agent({
  name: 'market_analyst_52',
  model: llmModel,
  instructions:
    'You are a market analyst. Analyze the market size, growth rate, ' +
    'and key players for the given topic. Be concise (3-4 bullet points).',
});

export const riskAnalyst = new Agent({
  name: 'risk_analyst_52',
  model: llmModel,
  instructions:
    'You are a risk analyst. Identify the top 3 risks: regulatory, ' +
    'technical, and competitive. Be concise.',
});

// Both analysts run concurrently
export const parallelResearch = new Agent({
  name: 'research_phase_52',
  model: llmModel,
  agents: [marketAnalyst, riskAnalyst],
  strategy: 'parallel',
});

// -- Sequential summarizer ---------------------------------------------------

export const summarizer = new Agent({
  name: 'summarizer_52',
  model: llmModel,
  instructions:
    'You are an executive briefing writer. Synthesize the market analysis ' +
    'and risk assessment into a concise executive summary (1 paragraph).',
});

// -- Pipeline: parallel research -> summary ----------------------------------

const pipeline = parallelResearch.pipe(summarizer);

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    pipeline,
    'Launching an AI-powered healthcare diagnostics tool in the US',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(pipeline);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents research_phase_52
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(pipeline);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('52-nested-strategies.ts') || process.argv[1]?.endsWith('52-nested-strategies.js')) {
  main().catch(console.error);
}
