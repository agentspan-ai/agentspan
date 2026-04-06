/**
 * Human Tool — LLM-initiated human interaction.
 *
 * Unlike approvalRequired tools (09-human-in-the-loop.ts) where humans gate
 * tool execution, humanTool lets the LLM **ask the human questions** at
 * any point. The LLM decides when to call the tool, and the human's response
 * is returned as the tool output.
 *
 * The tool is entirely server-side (Conductor HUMAN task) — no worker process
 * needed. The server generates the response form and validation pipeline
 * automatically, so this works with any SDK language.
 *
 * Demonstrates:
 *   - humanTool() for LLM-initiated human interaction
 *   - Mixing human tools with regular tools
 *   - The LLM using human input to make decisions
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
 *   - AGENTSPAN_LLM_MODEL (default: openai/gpt-4o-mini)
 */

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime, humanTool, tool } from '@agentspan-ai/sdk';
import type { AgentHandle } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

const lookupEmployee = tool(
  async (args: { name: string }) => {
    const employees: Record<
      string,
      { name: string; department: string; level: string }
    > = {
      alice: {
        name: 'Alice Chen',
        department: 'Engineering',
        level: 'Senior',
      },
      bob: {
        name: 'Bob Martinez',
        department: 'Sales',
        level: 'Manager',
      },
      carol: {
        name: 'Carol Wu',
        department: 'Engineering',
        level: 'Staff',
      },
    };
    const key = args.name.toLowerCase().split(' ')[0];
    return employees[key] ?? { error: `Employee '${args.name}' not found` };
  },
  {
    name: 'lookup_employee',
    description: 'Look up an employee by name and return their info.',
    inputSchema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Employee name to look up' },
      },
      required: ['name'],
    },
  },
);

const submitTicket = tool(
  async (args: { title: string; priority: string; assignee: string }) => {
    return {
      ticket_id: 'TKT-4821',
      title: args.title,
      priority: args.priority,
      assignee: args.assignee,
    };
  },
  {
    name: 'submit_ticket',
    description: 'Submit an IT support ticket.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Ticket title' },
        priority: { type: 'string', description: 'Priority level' },
        assignee: { type: 'string', description: 'Assignee name' },
      },
      required: ['title', 'priority', 'assignee'],
    },
  },
);

const askUser = humanTool({
  name: 'ask_user',
  description:
    'Ask the user a question when you need clarification or additional information.',
});

export const agent = new Agent({
  name: 'it_support',
  model: llmModel,
  tools: [lookupEmployee, submitTicket, askUser],
  instructions:
    'You are an IT support assistant. Help users create support tickets. ' +
    'Use lookup_employee to find employee info. ' +
    'If you need clarification about the issue or any details, use ask_user ' +
    'to ask the user directly. Always confirm the ticket details with the user ' +
    'before submitting.',
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
    'I need to file a ticket for Alice about a laptop issue',
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
  // const result = await runtime.run(agent, 'Look up Alice Chen and summarize her department and level.');
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
