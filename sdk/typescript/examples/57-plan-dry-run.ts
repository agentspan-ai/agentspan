/**
 * 57 - Plan (Dry Run) — compile an agent without executing it.
 *
 * Demonstrates:
 *   - runtime.plan() to compile an agent to a Conductor workflow
 *   - Inspecting the compiled workflow structure
 *   - CI/CD validation: verify agents compile correctly before deployment
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tools -------------------------------------------------------------------

const searchWeb = tool(
  async (args: { query: string }) => {
    return { query: args.query, results: ['result1', 'result2'] };
  },
  {
    name: 'search_web',
    description: 'Search the web for information.',
    inputSchema: z.object({
      query: z.string().describe('Search query string'),
    }),
  },
);

const writeReport = tool(
  async (args: { title: string; content: string }) => {
    return { section: `## ${args.title}\n\n${args.content}` };
  },
  {
    name: 'write_report',
    description: 'Write a section of a report.',
    inputSchema: z.object({
      title: z.string().describe('Section title'),
      content: z.string().describe('Section body text'),
    }),
  },
);

// -- Define the agent --------------------------------------------------------

export const agent = new Agent({
  name: 'research_writer',
  model: llmModel,
  instructions: 'You are a research writer. Research topics and write reports.',
  tools: [searchWeb, writeReport],
  maxTurns: 10,
});

// -- Plan: compile without executing -----------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('57-plan-dry-run.ts') || process.argv[1]?.endsWith('57-plan-dry-run.js')) {
  const runtime = new AgentRuntime();
  try {
    const workflowDef = await runtime.plan(agent);

    console.log(`Workflow name: ${workflowDef.name}`);
    const tasks: Array<Record<string, unknown>> = (workflowDef as Record<string, unknown>).tasks as Array<Record<string, unknown>> ?? [];
    console.log(`Total tasks:   ${tasks.length}`);
    console.log();

    // Walk the task tree
    for (const task of tasks) {
      console.log(`  [${task.type}] ${task.taskReferenceName}`);
      if (task.type === 'DO_WHILE' && Array.isArray(task.loopOver)) {
        for (const sub of task.loopOver as Array<Record<string, unknown>>) {
          console.log(`    [${sub.type}] ${sub.taskReferenceName}`);
        }
      }
    }

    // Full JSON for CI/CD validation or export
    console.log('\n--- Full workflow JSON ---');
    console.log(JSON.stringify(workflowDef, null, 2));
  } finally {
    await runtime.shutdown();
  }
}
