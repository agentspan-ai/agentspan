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
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
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
    // Start async so we can interact with the human tasks
    const handle: AgentHandle = await runtime.start(
      team,
      'Write a short paragraph about the history of artificial intelligence.',
    );
    console.log(`Started execution: ${handle.executionId}`);

    // In a real app, a UI would show the agent options and the human would pick.
    // Here we simulate by selecting agents programmatically:
    const selections = ['writer', 'editor', 'fact_checker'];

    for (let i = 0; i < selections.length; i++) {
      const agentName = selections[i];

      // Wait for the workflow to pause at the HumanTask
      let completed = false;
      let waiting = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        const status = await handle.getStatus();
        if (status.isComplete) {
          console.log(`Workflow completed after ${i} turns`);
          completed = true;
          break;
        }
        if (status.isWaiting) {
          waiting = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }

      if (completed) break;

      if (waiting) {
        console.log(`Turn ${i + 1}: Selecting '${agentName}'`);
        await handle.respond({ selected: agentName });
      }
    }

    // Wait for final completion
    for (let attempt = 0; attempt < 30; attempt++) {
      const status = await handle.getStatus();
      if (status.isComplete) {
        console.log(`\nFinal output:\n${JSON.stringify(status.output)}`);
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } finally {
    await runtime.shutdown();
  }
}
