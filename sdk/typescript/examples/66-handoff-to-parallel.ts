/**
 * 66 - Handoff to Parallel — delegate to a multi-agent group.
 *
 * A parent agent can hand off to either a single agent (quick check)
 * or a parallel multi-agent group (deep analysis).
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

// -- Quick check (single agent) ----------------------------------------------

export const quickCheck = new Agent({
  name: 'quick_check',
  model: llmModel,
  instructions: 'You provide quick, 1-sentence assessments. Be brief and direct.',
});

// -- Deep analysis (parallel group) ------------------------------------------

export const marketAnalyst = new Agent({
  name: 'market_analyst_66',
  model: llmModel,
  instructions:
    'You are a market analyst. Analyze the market opportunity: ' +
    'size, growth rate, key players. 3-4 bullet points.',
});

export const riskAnalyst = new Agent({
  name: 'risk_analyst_66',
  model: llmModel,
  instructions:
    'You are a risk analyst. Identify the top 3 risks: ' +
    'regulatory, technical, and competitive. 3-4 bullet points.',
});

export const deepAnalysis = new Agent({
  name: 'deep_analysis',
  model: llmModel,
  agents: [marketAnalyst, riskAnalyst],
  strategy: 'parallel',
});

// -- Coordinator with handoff ------------------------------------------------

export const coordinator = new Agent({
  name: 'coordinator_66',
  model: llmModel,
  instructions:
    'You are a business strategist. Route requests to the right team:\n' +
    '- quick_check for simple yes/no questions or quick assessments\n' +
    '- deep_analysis for comprehensive analysis requiring multiple perspectives',
  agents: [quickCheck, deepAnalysis],
  strategy: 'handoff',
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(coordinator);
    // await runtime.serve(coordinator);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    // Scenario 1: Deep analysis (handoff to parallel group)
    console.log('='.repeat(60));
    console.log('  Scenario 1: Deep analysis (handoff -> parallel group)');
    console.log('='.repeat(60));
    const result = await runtime.run(
    coordinator,
    'Provide a deep analysis of entering the AI healthcare market.',
    );
    result.printResult();

    if (result.status === 'COMPLETED') {
    console.log('[OK] Handoff to parallel group completed successfully');
    } else {
    console.log(`[WARN] Unexpected status: ${result.status}`);
    }

    // Scenario 2: Quick check (handoff to single agent)
    console.log('\n' + '='.repeat(60));
    console.log('  Scenario 2: Quick check (handoff -> single agent)');
    console.log('='.repeat(60));
    const result2 = await runtime.run(
    coordinator,
    'Is the mobile app market still growing?',
    );
    result2.printResult();

    if (result2.status === 'COMPLETED') {
    console.log('[OK] Quick check completed successfully');
    } else {
    console.log(`[WARN] Unexpected status: ${result2.status}`);
    }
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('66-handoff-to-parallel.ts') || process.argv[1]?.endsWith('66-handoff-to-parallel.js')) {
  main().catch(console.error);
}
