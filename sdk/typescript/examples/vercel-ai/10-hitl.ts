/**
 * Vercel AI SDK Tools + Native Agent -- Human-in-the-Loop (HITL)
 *
 * Demonstrates approval_required on tools with a native agentspan Agent.
 * When a tool has approvalRequired: true, the agent pauses for human approval
 * before executing the tool. The direct-run path uses runtime.run() so the
 * example works as-is, and a commented runtime.start() alternative shows the
 * async approval/reject flow via the AgentHandle.
 *
 * This example mixes Vercel AI SDK tool() (for risk assessment, auto-execute)
 * and agentspan native tool() (for action execution, requires approval).
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  tool as agentspanTool,
} from '../../src/index.js';

// ── Risk assessment tool (AI SDK, auto-execute) ──────────
const assessRisk = aiTool({
  description: 'Assess the risk level of a requested operation.',
  parameters: z.object({
    action: z.string().describe('The action to assess'),
    description: z.string().describe('Description of what the action will do'),
  }),
  execute: async ({ action, description }) => {
    let risk: 'low' | 'medium' | 'high' = 'low';
    const lower = `${action} ${description}`.toLowerCase();

    if (lower.includes('delete') || lower.includes('drop') || lower.includes('destroy')) {
      risk = 'high';
    } else if (lower.includes('update') || lower.includes('modify') || lower.includes('change')) {
      risk = 'medium';
    }

    return { action, risk };
  },
});

// ── Execution tool (agentspan native, requires approval) ─
const executeAction = agentspanTool(
  async (args: { action: string }) => ({
    status: 'completed',
    message: `Action "${args.action}" executed successfully.`,
  }),
  {
    name: 'execute_action',
    description: 'Execute an approved action. Only call this after risk assessment.',
    inputSchema: z.object({
      action: z.string().describe('The approved action to execute'),
    }),
    approvalRequired: true, // Pauses for human approval
  },
);

// ── Native Agent with HITL tools ─────────────────────────
export const agent = new Agent({
  name: 'hitl_agent',
  model: 'openai/gpt-4o-mini',
  instructions:
    'You are a careful assistant that assesses risk before taking action.\n' +
    'For every user request:\n' +
    '1. First use assessRisk to evaluate the operation\n' +
    '2. Then use execute_action to carry it out (requires human approval)\n' +
    '3. Report the outcome\n' +
    'Never execute an action without assessing its risk first.',
  tools: [assessRisk, executeAction],
  maxTurns: 6,
});

// ── Test cases ───────────────────────────────────────────
const testCases = [
  { label: 'Low risk (should be approved)', prompt: 'Fetch the latest sales report for Q4 2024.' },
  { label: 'Medium risk (should be approved)', prompt: 'Update the customer email address for account #12345.' },
  { label: 'High risk (should be rejected)', prompt: 'Delete all records from the staging database.' },
];

// ── HITL simulation: auto-approve low/medium, reject high ─
async function runWithApproval(runtime: AgentRuntime, prompt: string) {
  const handle = await runtime.start(agent, prompt);
  const MAX_POLLS = 30;
  let polls = 0;

  // Poll until done or waiting for approval
  while (polls < MAX_POLLS) {
    polls++;
    const status = await handle.getStatus();

    if (status.isComplete) {
      return await handle.wait();
    }

    if (status.isWaiting) {
      // Check if there is a pending tool requiring approval
      const pending = status.pendingTool;
      if (pending && pending.args) {
        const action = String(pending.args.action ?? pending.name ?? '');
        const lower = action.toLowerCase();

        if (lower.includes('delete') || lower.includes('drop')) {
          console.log(`  [HITL] Rejecting: "${action}"`);
          await handle.reject('High-risk action rejected by human reviewer.');
        } else {
          console.log(`  [HITL] Approving: "${action}"`);
          await handle.approve();
        }
      } else {
        // Waiting but no pending tool details -- auto-approve to unblock
        console.log('  [HITL] Waiting (no pending tool details) -- auto-approving');
        await handle.approve();
      }
    }

    // Brief wait before next poll
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  // If we exhaust polls, wait for final result
  return await handle.wait();
}

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      'Explain how you decide whether an operation should be approved before execution.',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/vercel-ai --agents hitl_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
    //
    // Interactive HITL alternative:
    // for (const { label, prompt } of testCases) {
    //   console.log(`\n--- ${label} ---`);
    //   const interactiveResult = await runWithApproval(runtime, prompt);
    //   interactiveResult.printResult();
    // }
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('10-hitl.ts') || process.argv[1]?.endsWith('10-hitl.js')) {
  main().catch(console.error);
}
