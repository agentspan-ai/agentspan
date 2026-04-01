// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent with Dynamic Instructions -- callable instruction function.
 *
 * Demonstrates:
 *   - Using a function for dynamic instructions
 *   - Instructions that change based on context (time of day, user info, etc.)
 *   - Function tools alongside dynamic instructions
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, tool, setTracingDisabled } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Dynamic instructions function ───────────────────────────────────

function getDynamicInstructions(_ctx: unknown, _agent: unknown): string {
  const hour = new Date().getHours();
  let greetingStyle: string;
  let tone: string;

  if (hour < 12) {
    greetingStyle = 'cheerful morning';
    tone = 'energetic and upbeat';
  } else if (hour < 17) {
    greetingStyle = 'professional afternoon';
    tone = 'focused and efficient';
  } else {
    greetingStyle = 'relaxed evening';
    tone = 'calm and conversational';
  }

  const timeStr = new Date().toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  return (
    `You are a personal assistant with a ${greetingStyle} style. ` +
    `Respond in a ${tone} tone. ` +
    `Current time: ${timeStr}. ` +
    `Always be helpful and use available tools when appropriate.`
  );
}

// ── Tools ───────────────────────────────────────────────────────────

const getTodoList = tool({
  name: 'get_todo_list',
  description: "Get the user's current todo list.",
  parameters: z.object({}),
  execute: async () => {
    const todos = [
      'Review PR #42 -- high priority',
      'Write unit tests for auth module',
      'Team standup at 2pm',
      'Deploy v2.1 to staging',
    ];
    return todos.map((t) => `- ${t}`).join('\n');
  },
});

const addTodo = tool({
  name: 'add_todo',
  description: 'Add a new item to the todo list.',
  parameters: z.object({
    task: z.string().describe('Task description'),
    priority: z.string().default('medium').describe('Priority level'),
  }),
  execute: async ({ task, priority }) => {
    return `Added to todo list: '${task}' (priority: ${priority})`;
  },
});

// ── Agent ───────────────────────────────────────────────────────────

export const agent = new Agent({
  name: 'personal_assistant',
  instructions: getDynamicInstructions,
  model: 'gpt-4o-mini',
  tools: [getTodoList, addTodo],
});

const prompt = "Show me my todo list and add 'Prepare demo for Friday' as high priority.";

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('09-dynamic-instructions.ts') || process.argv[1]?.endsWith('09-dynamic-instructions.js')) {
  main().catch(console.error);
}
