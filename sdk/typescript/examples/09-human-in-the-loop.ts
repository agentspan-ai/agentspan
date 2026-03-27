/**
 * Human-in-the-Loop — approval workflows.
 *
 * Demonstrates how tools with approvalRequired=true pause the workflow
 * until a human approves or rejects the action. A Conductor HumanTask is
 * inserted into the compiled workflow so the loop pauses at the right point
 * and resumes after the reviewer decides.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import type { AgentHandle } from '../src/index.js';
import { llmModel } from './settings.js';

const checkBalance = tool(
  async (args: { accountId: string }) => {
    return { account_id: args.accountId, balance: 15000.0 };
  },
  {
    name: 'check_balance',
    description: 'Check the balance of an account.',
    inputSchema: z.object({
      accountId: z.string().describe('The account ID'),
    }),
  },
);

const transferFunds = tool(
  async (args: { fromAcct: string; toAcct: string; amount: number }) => {
    return {
      status: 'completed',
      from: args.fromAcct,
      to: args.toAcct,
      amount: args.amount,
    };
  },
  {
    name: 'transfer_funds',
    description: 'Transfer funds between accounts. Requires human approval.',
    inputSchema: z.object({
      fromAcct: z.string().describe('Source account'),
      toAcct: z.string().describe('Destination account'),
      amount: z.number().describe('Amount to transfer'),
    }),
    approvalRequired: true,
  },
);

export const agent = new Agent({
  name: 'banker',
  model: llmModel,
  tools: [checkBalance, transferFunds],
  instructions:
    'You are a banking assistant. Help with balance inquiries and transfers.',
});

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('09-human-in-the-loop.ts') || process.argv[1]?.endsWith('09-human-in-the-loop.js')) {
  const runtime = new AgentRuntime();
  try {
    // start() returns a handle; handle.stream() streams events with HITL support
    const handle: AgentHandle = await runtime.start(
      agent,
      'Transfer $500 from ACC-789 to ACC-456',
    );
    console.log(`Workflow started: ${handle.workflowId}\n`);

    for await (const event of handle.stream()) {
      switch (event.type) {
        case 'thinking':
          console.log(`  [thinking] ${event.content}`);
          break;

        case 'tool_call':
          console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
          break;

        case 'tool_result':
          console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result)}`);
          break;

        case 'waiting':
          console.log(`\n--- Human approval required ---`);
          // Auto-approve since we can't do interactive stdin
          console.log('  Auto-approving for demo...');
          await handle.approve();
          console.log('  Approved!\n');
          break;

        case 'error':
          console.log(`  [error] ${event.content}`);
          break;

        case 'done':
          console.log(`\nResult: ${JSON.stringify(event.output)}`);
          break;
      }
    }
  } finally {
    await runtime.shutdown();
  }
}
