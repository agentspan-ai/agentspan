/**
 * 47 - Callbacks — composable lifecycle hooks around LLM and tool calls.
 *
 * Demonstrates a `CallbackHandler` subclass (passed via `callbacks: [...]`)
 * to intercept and inspect agent/model/tool lifecycle events.
 *
 * Requirements:
 *   - Conductor server with callback support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, CallbackHandler, tool } from '@conductor-oss/conductor-agent-sdk';
import { llmModel } from './settings';

// -- Callback handler --------------------------------------------------------

class MonitorCallbacks extends CallbackHandler {
  async onModelStart(agentName: string, messages: unknown[]): Promise<void> {
    console.log(`  [before_model] ${agentName}: sending ${messages.length} messages to LLM`);
  }

  async onModelEnd(agentName: string, response: unknown): Promise<void> {
    const length = typeof response === 'string' ? response.length : JSON.stringify(response ?? '').length;
    console.log(`  [after_model] ${agentName}: LLM returned ${length} characters`);
  }

  async onToolStart(agentName: string, toolName: string, args: unknown): Promise<void> {
    console.log(`  [before_tool] ${agentName}: calling ${toolName}(${JSON.stringify(args)})`);
  }
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
    inputSchema: {
      type: 'object',
      properties: {
        topic: { type: 'string', description: 'The topic to get facts about' },
      },
      required: ['topic'],
    },
  },
);

// -- Agent with callbacks ----------------------------------------------------

export const agent = new Agent({
  name: 'monitored_agent_47',
  model: llmModel,
  instructions: 'You are a helpful assistant. Use get_facts when asked about topics.',
  tools: [getFacts],
  callbacks: [new MonitorCallbacks()],
});

// -- Run ---------------------------------------------------------------------

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Tell me interesting facts about AI and space.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents monitored_agent_47
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
