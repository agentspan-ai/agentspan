/**
 * Manual Selection -- human picks which agent speaks next.
 *
 * Demonstrates strategy: 'manual' where the workflow pauses each turn
 * to let a human select which agent should respond. The human interacts
 * via the AgentHandle.respond() API.
 *
 * Flow:
 *   1. Workflow pauses with a HumanTask showing available agents
 *   2. Human picks an agent (e.g. { selected: "writer" })
 *   3. Selected agent responds
 *   4. Repeat until max_turns
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src';
import type { AgentHandle } from '../src/index.js';
import { llmModel } from './settings.js';

export const writer = new Agent({
  name: 'writer',
  model: llmModel,
  instructions: 'You are a creative writer. Expand on ideas with vivid prose.',
});

export const editor = new Agent({
  name: 'editor',
  model: llmModel,
  instructions: 'You are a strict editor. Improve clarity, fix issues, tighten prose.',
});

export const factChecker = new Agent({
  name: 'fact_checker',
  model: llmModel,
  instructions: 'You verify claims and flag anything inaccurate or unsupported.',
});

// Manual strategy: human picks who speaks each turn
export const team = new Agent({
  name: 'editorial_team',
  model: llmModel,
  agents: [writer, editor, factChecker],
  strategy: 'manual',
  maxTurns: 3,
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('18-manual-selection.ts') || process.argv[1]?.endsWith('18-manual-selection.js')) {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      writer,
      'Write a short paragraph about the history of artificial intelligence.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(team);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(team);
    //
    // Interactive manual-selection alternative:
    // const handle: AgentHandle = await runtime.start(
    //   team,
    //   'Write a short paragraph about the history of artificial intelligence.',
    // );
    // await handle.respond({ selected: 'writer' });
  } finally {
    await runtime.shutdown();
  }
}
