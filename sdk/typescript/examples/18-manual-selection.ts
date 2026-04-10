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

import * as readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { Agent, AgentRuntime } from '@agentspan-ai/sdk';
import type { AgentHandle } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

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

// -- Helpers ------------------------------------------------------------------

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

// -- Run ----------------------------------------------------------------------

const rl = readline.createInterface({ input: stdin, output: stdout });
const runtime = new AgentRuntime();
try {
  const handle = await runtime.start(
    team,
    'Write a short paragraph about the history of artificial intelligence.',
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
  // const result = await runtime.run(writer, 'Write a short paragraph about the history of artificial intelligence.');
  // result.printResult();

  // Production pattern:
  // 1. Deploy once during CI/CD:
  // await runtime.deploy(team);
  //
  // 2. In a separate long-lived worker process:
  // await runtime.serve(team);
} finally {
  rl.close();
  await runtime.shutdown();
}
