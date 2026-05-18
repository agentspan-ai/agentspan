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

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

const checkBalance = tool(
  async (args: { accountId: string }) => {
    return { account_id: args.accountId, balance: 15000.0 };
  },
  {
    name: 'check_balance',
    description: 'Check the balance of an account.',
    inputSchema: {
      type: 'object',
      properties: {
        accountId: { type: 'string', description: 'The account ID' },
      },
      required: ['accountId'],
    },
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
    inputSchema: {
      type: 'object',
      properties: {
        fromAcct: { type: 'string', description: 'Source account' },
        toAcct: { type: 'string', description: 'Destination account' },
        amount: { type: 'number', description: 'Amount to transfer' },
      },
      required: ['fromAcct', 'toAcct', 'amount'],
    },
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

async function promptHuman(
  rl: readline.Interface,
  pendingTool: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const schema = (pendingTool.response_schema ?? {}) as Record<string, unknown>;
  const props = (schema.properties ?? {}) as Record<string, Record<string, unknown>>;
  const response: Record<string, unknown> = {};
  for (const [field, fs] of Object.entries(props)) {
    const desc = (fs.description || fs.title || field) as string;
    if (fs.type === 'boolean') {
      const val = await rl.question(`  ${desc} (y/n): `);
      response[field] = ['y', 'yes'].includes(val.trim().toLowerCase());
    } else {
      response[field] = await rl.question(`  ${desc}: `);
    }
  }
  return response;
}

const rl = readline.createInterface({ input: stdin, output: stdout });
const runtime = new AgentRuntime();
try {
  const handle = await runtime.start(
    agent,
    'Transfer $500 from ACC-789 to ACC-456. Check the balance first.',
  );
  console.log(`Started: ${handle.executionId}\n`);

  for await (const event of handle.stream()) {
    if (event.type === 'thinking') {
      console.log(`  [thinking] ${event.content}`);
    } else if (event.type === 'tool_call') {
      console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
    } else if (event.type === 'tool_result') {
      console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result).slice(0, 100)}`);
    } else if (event.type === 'waiting') {
      const status = await handle.getStatus();
      const pt = (status.pendingTool ?? {}) as Record<string, unknown>;
      console.log('\n--- Human input required ---');
      const response = await promptHuman(rl, pt);
      await handle.respond(response);
      console.log();
    } else if (event.type === 'done') {
      console.log(`\nDone: ${JSON.stringify(event.output)}`);
    }
  }

  // Non-interactive alternative (no HITL, will block on human tasks):
  // const result = await runtime.run(agent, "What's the balance on ACC-789?");
  // result.printResult();

  // Production pattern:
  // 1. Deploy once during CI/CD:
  // await runtime.deploy(agent);
  //
  // 2. In a separate long-lived worker process:
  // await runtime.serve(agent);
} finally {
  rl.close();
  await runtime.shutdown();
}
