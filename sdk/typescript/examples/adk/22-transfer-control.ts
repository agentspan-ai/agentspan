/**
 * Google ADK Transfer Control -- restricted agent handoffs.
 *
 * Demonstrates:
 *   - disallowTransferToParent: prevents sub-agent from returning to parent
 *   - disallowTransferToPeers: prevents sub-agent from transferring to siblings
 *   - These map to allowedTransitions in the server workflow
 *
 * Architecture:
 *   coordinator (parent)
 *     subAgents:
 *       - specialist_a (can only talk to specialist_b, not parent)
 *       - specialist_b (can talk to anyone)
 *       - specialist_c (can only talk to parent, not peers)
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Specialist agents with transfer restrictions ────────────────────

export const specialistA = new LlmAgent({
  name: 'data_collector',
  model,
  instruction:
    'You are a data collection specialist. Gather relevant data points ' +
    'about the topic and pass them to the analyst for analysis. ' +
    'You should NOT return to the coordinator directly.',
  disallowTransferToParent: true,
});

export const specialistB = new LlmAgent({
  name: 'analyst',
  model,
  instruction:
    'You are a data analyst. Take the data collected and provide ' +
    'a concise analysis with insights. You can transfer to any agent.',
});

export const specialistC = new LlmAgent({
  name: 'summarizer',
  model,
  instruction:
    'You are a summarizer. Take the analysis and create a brief ' +
    'executive summary. Return the summary to the coordinator. ' +
    'Do NOT transfer to other specialists.',
  disallowTransferToPeers: true,
});

// ── Coordinator ───────────────────────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'research_coordinator',
  model,
  instruction:
    'You are a research coordinator managing a team of specialists:\n' +
    '- data_collector: gathers raw data (cannot return to you directly)\n' +
    '- analyst: analyzes data (can transfer freely)\n' +
    '- summarizer: creates executive summaries (cannot transfer to peers)\n\n' +
    "Route the user's request through the appropriate workflow.",
  subAgents: [specialistA, specialistB, specialistC],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(coordinator);
    // await runtime.serve(coordinator);
    // Direct run for local development:
    const result = await runtime.run(
    coordinator,
    'Research the current state of renewable energy adoption worldwide.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('22-transfer-control.ts') || process.argv[1]?.endsWith('22-transfer-control.js')) {
  main().catch(console.error);
}
