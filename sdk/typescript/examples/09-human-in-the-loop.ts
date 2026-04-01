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
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
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
    description:
      'Request a funds transfer; runtime pauses for human approval before execution.',
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
    'You are a banking assistant. Use check_balance for balance inquiries. ' +
    'When asked to transfer money, first check the balance, then call ' +
    'transfer_funds to request the transfer. The runtime will pause for ' +
    'human approval before the transfer executes.',
});

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('09-human-in-the-loop.ts') || process.argv[1]?.endsWith('09-human-in-the-loop.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, "What's the balance on ACC-789?");
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
    //
    // Interactive HITL alternative:
    // const result = runtime.stream(
    //   agent,
    //   'Transfer $500 from ACC-789 to ACC-456. ' +
    //     'Check the balance first, then use transfer_funds.',
    // );
    // for await (const event of result) {
    //   if (event.type === 'waiting') await result.approve();
    // }
  } finally {
    await runtime.shutdown();
  }
}
