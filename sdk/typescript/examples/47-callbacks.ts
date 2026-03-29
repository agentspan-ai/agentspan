/**
 * 47 - Callbacks — lifecycle hooks before and after LLM calls.
 *
 * Demonstrates using `beforeModelCallback` and `afterModelCallback`
 * to intercept and inspect LLM interactions.
 *
 * Requirements:
 *   - Conductor server with callback support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Callback functions ------------------------------------------------------

function logBeforeModel(kwargs: { messages?: unknown[] }): Record<string, unknown> {
  const msgCount = kwargs.messages?.length ?? 0;
  console.log(`  [before_model] Sending ${msgCount} messages to LLM`);
  return {}; // Continue to LLM
}

function inspectAfterModel(kwargs: { llmResult?: string }): Record<string, unknown> {
  const length = kwargs.llmResult?.length ?? 0;
  console.log(`  [after_model] LLM returned ${length} characters`);
  return {}; // Keep original response
}

// -- Tool --------------------------------------------------------------------

const getFacts = tool(
  async (args: { topic: string }) => {
    const facts: Record<string, string[]> = {
      ai: ['AI was coined in 1956', 'GPT-4 has ~1.7T parameters'],
      space: ['The ISS orbits at 17,500 mph', 'Mars has the tallest volcano'],
    };
    for (const [key, vals] of Object.entries(facts)) {
      if (args.topic.toLowerCase().includes(key)) {
        return { topic: args.topic, facts: vals };
      }
    }
    return { topic: args.topic, facts: ['No specific facts found.'] };
  },
  {
    name: 'get_facts',
    description: 'Get interesting facts about a topic.',
    inputSchema: z.object({
      topic: z.string().describe('The topic to get facts about'),
    }),
  },
);

// -- Agent with callbacks ----------------------------------------------------

export const agent = new Agent({
  name: 'monitored_agent_47',
  model: llmModel,
  instructions: 'You are a helpful assistant. Use get_facts when asked about topics.',
  tools: [getFacts],
  beforeModelCallback: logBeforeModel,
  afterModelCallback: inspectAfterModel,
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(agent, 'Tell me interesting facts about AI and space.');
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('47-callbacks.ts') || process.argv[1]?.endsWith('47-callbacks.js')) {
  main().catch(console.error);
}
