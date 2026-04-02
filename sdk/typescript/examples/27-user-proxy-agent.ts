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

import { Agent, AgentRuntime, UserProxyAgent } from '../src/index.js';
import type { AgentHandle } from '../src/index.js';
import { llmModel } from './settings.js';

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

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('27-user-proxy-agent.ts') || process.argv[1]?.endsWith('27-user-proxy-agent.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      assistant,
      "Write a Python function to sort a list of dictionaries by a key.",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(conversation);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(conversation);
    //
    // Interactive user-proxy alternative:
    // const handle: AgentHandle = await runtime.start(
    //   conversation,
    //   "Let's write a Python function to sort a list of dictionaries by a key.",
    // );
    // await handle.respond({ message: 'Add type hints and a docstring.' });
  } finally {
    await runtime.shutdown();
  }
}
