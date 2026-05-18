/**
 * UserProxyAgent -- human stand-in for interactive conversations.
 *
 * Demonstrates `UserProxyAgent` which acts as a human proxy in
 * multi-agent conversations.  When it's the proxy's turn, the workflow
 * pauses for real human input.
 *
 * Modes:
 *   - ALWAYS: always pause for human input
 *   - TERMINATE: pause only when conversation would end
 *   - NEVER: auto-respond (useful for testing)
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime, UserProxyAgent } from '@agentspan-ai/sdk';
import type { AgentHandle } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Human proxy -----------------------------------------------------------

const human = new UserProxyAgent({
  name: 'human',
  mode: 'ALWAYS',
});

// -- AI assistant ----------------------------------------------------------

export const assistant = new Agent({
  name: 'assistant',
  model: llmModel,
  instructions:
    'You are a helpful coding assistant. Help the user write Python code. ' +
    'Ask clarifying questions when needed.',
});

// -- Round-robin conversation: human and assistant take turns ---------------

export const conversation = new Agent({
  name: 'pair_programming',
  model: llmModel,
  agents: [human, assistant],
  strategy: 'round_robin',
  maxTurns: 4, // 2 exchanges (human, assistant, human, assistant)
});

// -- Helpers ----------------------------------------------------------------

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

// -- Run -------------------------------------------------------------------

const rl = readline.createInterface({ input: stdin, output: stdout });
const runtime = new AgentRuntime();
try {
  const handle = await runtime.start(
    conversation,
    "Let's write a Python function to sort a list of dictionaries by a key.",
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
  // const result = await runtime.run(assistant, 'Write a Python function to sort a list of dictionaries by a key.');
  // result.printResult();

  // Production pattern:
  // 1. Deploy once during CI/CD:
  // await runtime.deploy(conversation);
  //
  // 2. In a separate long-lived worker process:
  // await runtime.serve(conversation);
} finally {
  rl.close();
  await runtime.shutdown();
}
