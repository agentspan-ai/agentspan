/**
 * Random Strategy -- random agent selection each turn.
 *
 * Demonstrates the strategy: 'random' pattern where a random sub-agent
 * is selected each iteration. Unlike round-robin (fixed rotation), random
 * selection adds variety -- useful for brainstorming or diverse perspectives.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

export const creative = new Agent({
  name: 'creative',
  model: llmModel,
  instructions:
    'You are a creative thinker. Suggest innovative, unconventional ideas. ' +
    'Keep your response to 2-3 sentences.',
});

export const practical = new Agent({
  name: 'practical',
  model: llmModel,
  instructions:
    'You are a practical thinker. Focus on feasibility and cost-effectiveness. ' +
    'Keep your response to 2-3 sentences.',
});

export const critical = new Agent({
  name: 'critical',
  model: llmModel,
  instructions:
    'You are a critical thinker. Identify risks and potential issues. ' +
    'Keep your response to 2-3 sentences.',
});

// Random selection: each turn, one of the three agents is picked at random
export const brainstorm = new Agent({
  name: 'brainstorm',
  model: llmModel,
  agents: [creative, practical, critical],
  strategy: 'random',
  maxTurns: 6,
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    brainstorm,
    'How should we approach building an AI-powered customer service platform?',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(brainstorm);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents brainstorm
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(brainstorm);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('16-random-strategy.ts') || process.argv[1]?.endsWith('16-random-strategy.js')) {
  main().catch(console.error);
}
