/**
 * Parallel Agents — fan-out / fan-in.
 *
 * Demonstrates the parallel strategy where all sub-agents run concurrently
 * on the same input and their results are aggregated.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Specialist analysts -----------------------------------------------------

const marketAnalyst = new Agent({
  name: 'market_analyst',
  model: llmModel,
  instructions:
    'You are a market analyst. Analyze the given topic from a market perspective: ' +
    'market size, growth trends, key players, and opportunities.',
});

const riskAnalyst = new Agent({
  name: 'risk_analyst',
  model: llmModel,
  instructions:
    'You are a risk analyst. Analyze the given topic for risks: ' +
    'regulatory risks, technical risks, competitive threats, and mitigation strategies.',
});

const complianceChecker = new Agent({
  name: 'compliance',
  model: llmModel,
  instructions:
    'You are a compliance specialist. Check the given topic for compliance considerations: ' +
    'data privacy, regulatory requirements, and industry standards.',
});

// -- Parallel analysis -------------------------------------------------------

const analysis = new Agent({
  name: 'analysis',
  model: llmModel,
  agents: [marketAnalyst, riskAnalyst, complianceChecker],
  strategy: 'parallel',
});

const runtime = new AgentRuntime();
try {
  const result = await runtime.run(
    analysis,
    'Launching an AI-powered healthcare diagnostic tool in the US market',
  );
  result.printResult();
} finally {
  await runtime.shutdown();
}
