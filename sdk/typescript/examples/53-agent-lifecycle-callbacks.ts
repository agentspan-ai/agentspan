/**
 * 53 - Agent Lifecycle Callbacks — composable handler classes.
 *
 * Demonstrates using CallbackHandler subclasses to hook into agent
 * and model lifecycle events. Multiple handlers chain per-position
 * in list order.
 *
 * Requirements:
 *   - Conductor server with callback support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, CallbackHandler, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Handler 1: Timing -------------------------------------------------------

class TimingHandler extends CallbackHandler {
  private t0 = 0;

  onAgentStart(_kwargs: Record<string, unknown>) {
    this.t0 = Date.now();
    console.log('  [timing] Agent started');
  }

  onAgentEnd(_kwargs: Record<string, unknown>) {
    const elapsed = ((Date.now() - this.t0) / 1000).toFixed(2);
    console.log(`  [timing] Agent finished -- ${elapsed}s`);
  }
}

// -- Handler 2: Logging ------------------------------------------------------

class LoggingHandler extends CallbackHandler {
  onModelStart(kwargs: { messages?: unknown[] }) {
    console.log(`  [log] Sending ${(kwargs.messages ?? []).length} messages to LLM`);
  }

  onModelEnd(kwargs: { llmResult?: string }) {
    const snippet = (kwargs.llmResult ?? '').slice(0, 80);
    console.log(`  [log] LLM responded: "${snippet}"`);
  }

  onToolStart(_kwargs: Record<string, unknown>) {
    console.log('  [log] Tool executing...');
  }

  onToolEnd(_kwargs: Record<string, unknown>) {
    console.log('  [log] Tool finished');
  }
}

// -- Tool --------------------------------------------------------------------

const lookupWeather = tool(
  async (args: { city: string }) => {
    return { city: args.city, temperature: '22C', condition: 'sunny' };
  },
  {
    name: 'lookup_weather',
    description: 'Get the current weather for a city.',
    inputSchema: z.object({
      city: z.string().describe('Name of the city'),
    }),
  },
);

// -- Agent with chained handlers ---------------------------------------------

export const agent = new Agent({
  name: 'lifecycle_agent_53',
  model: llmModel,
  instructions: 'You are a helpful assistant. Use lookup_weather for weather queries.',
  tools: [lookupWeather],
  callbacks: [new TimingHandler(), new LoggingHandler()],
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(agent, "What's the weather like in Tokyo?");
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('53-agent-lifecycle-callbacks.ts') || process.argv[1]?.endsWith('53-agent-lifecycle-callbacks.js')) {
  main().catch(console.error);
}
