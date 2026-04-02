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

import { z } from 'zod';
import { Agent, AgentRuntime, humanTool, tool } from '../src/index.js';
import type { AgentHandle } from '../src/index.js';
import { llmModel } from './settings.js';

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
    inputSchema: z.object({
      name: z.string().describe('Employee name to look up'),
    }),
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
    inputSchema: z.object({
      title: z.string().describe('Ticket title'),
      priority: z.string().describe('Priority level'),
      assignee: z.string().describe('Assignee name'),
    }),
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

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('09d-human-tool.ts') || process.argv[1]?.endsWith('09d-human-tool.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      'Look up Alice Chen and summarize her department and level.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents it_support
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);

    // Interactive human-tool alternative:
    // const handle: AgentHandle = await runtime.start(
    //   agent,
    //   'I need to file a ticket for Alice about a laptop issue',
    // );
    // console.log(`Execution started: ${handle.executionId}\n`);
    // for await (const event of handle.stream()) {
    //   if (event.type === 'waiting') {
    //     await handle.respond({
    //       response:
    //         'The laptop screen is flickering, high priority please',
    //     });
    //   }
    // }
  } finally {
    await runtime.shutdown();
  }
}
