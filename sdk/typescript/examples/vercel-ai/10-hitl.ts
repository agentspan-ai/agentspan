/**
 * Vercel AI SDK Tools + Native Agent -- Human-in-the-Loop (HITL)
 *
 * Demonstrates approval_required on tools with a native agentspan Agent.
 * When a tool has approvalRequired: true, the agent pauses for human approval
 * before executing the tool. Uses interactive streaming with schema-driven
 * console prompts to handle the HITL pause.
 *
 * This example mixes Vercel AI SDK tool() (for risk assessment, auto-execute)
 * and agentspan native tool() (for action execution, requires approval).
 */

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { tool as aiTool } from 'ai';
import { z } from 'zod';
import {
  Agent,
  AgentRuntime,
  tool as agentspanTool,
} from '@agentspan-ai/sdk';

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

// ── Helpers ──────────────────────────────────────────────
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

// ── Run on agentspan ─────────────────────────────────────

const rl = readline.createInterface({ input: stdin, output: stdout });
const runtime = new AgentRuntime();
try {
  const handle = await runtime.start(
    agent,
    'Fetch the latest sales report for Q4 2024.',
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
  // const result = await runtime.run(agent, 'Explain how you decide whether an operation should be approved before execution.');
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
