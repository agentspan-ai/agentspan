/**
 * Swarm Orchestration -- automatic agent transitions via transfer tools.
 *
 * Demonstrates strategy: 'swarm' with LLM-driven, tool-based handoffs.
 * Each agent gets transfer_to_<peer> tools and the LLM decides when to
 * hand off by calling the appropriate transfer tool.
 *
 * Condition-based handoffs (OnTextMention, etc.) remain as optional fallback
 * when no transfer tool is called.
 *
 * Flow:
 *   1. Parent support agent triages the initial request
 *   2. Support agent sees tools: [transfer_to_refund_specialist, transfer_to_tech_support]
 *   3. LLM calls transfer_to_refund_specialist() -> inner loop exits
 *   4. Handoff check detects transfer -> active agent switches
 *   5. Refund specialist handles the request (no transfer) -> loop exits
 *   6. Output: refund specialist's clean response
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, OnTextMention } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Specialist agents --------------------------------------------------------

export const refundAgent = new Agent({
  name: 'refund_specialist',
  model: llmModel,
  instructions:
    "You are a refund specialist. Process the customer's refund request. " +
    'Check eligibility, confirm the refund amount, and let them know the ' +
    'timeline. Be empathetic and clear. Do NOT ask follow-up questions -- ' +
    'just process the refund based on what the customer told you.',
});

export const techAgent = new Agent({
  name: 'tech_support',
  model: llmModel,
  instructions:
    "You are a technical support specialist. Diagnose the customer's " +
    'technical issue and provide clear troubleshooting steps.',
});

// -- Front-line support agent with swarm handoffs -----------------------------

export const support = new Agent({
  name: 'support',
  model: llmModel,
  instructions:
    'You are the front-line customer support agent. Triage customer requests. ' +
    'If the customer needs a refund, transfer to the refund specialist. ' +
    'If they have a technical issue, transfer to tech support. ' +
    'Use the transfer tools available to you to hand off the conversation.',
  agents: [refundAgent, techAgent],
  strategy: 'swarm',
  handoffs: [
    // Fallback condition-based handoffs (evaluated only if no transfer tool was called)
    new OnTextMention({ text: 'refund', target: 'refund_specialist' }),
    new OnTextMention({ text: 'technical', target: 'tech_support' }),
  ],
  maxTurns: 3,
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('--- Refund scenario ---');
    const result = await runtime.run(
    support,
    'I bought a product last week and it arrived damaged. I want my money back.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(support);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents support
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(support);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('17-swarm-orchestration.ts') || process.argv[1]?.endsWith('17-swarm-orchestration.js')) {
  main().catch(console.error);
}
