/**
 * Composable Termination Conditions -- AND/OR rules for stopping agents.
 *
 * Demonstrates composable termination conditions using `.and()` (AND) and
 * `.or()` (OR) operators.  Conditions include:
 *
 * - TextMention: stop when output contains specific text
 * - StopMessage: stop on exact match (e.g. "TERMINATE")
 * - MaxMessage: stop after N messages
 * - TokenUsageCondition: stop when token budget exceeded
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import {
  Agent,
  AgentRuntime,
  tool,
  TextMention,
  StopMessage,
  MaxMessage,
  TokenUsageCondition,
} from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Simple text mention ----------------------------------------

const search = tool(
  async (args: { query: string }) => {
    return `Results for '${args.query}': AI agents are software programs that act autonomously.`;
  },
  {
    name: 'search',
    description: 'Search for information.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The search query' },
      },
      required: ['query'],
    },
  },
);

export const agent1 = new Agent({
  name: 'researcher',
  model: llmModel,
  tools: [search],
  instructions: 'Research the topic and say DONE when you have enough info.',
  termination: new TextMention('DONE'),
});

// -- Example 2: OR -- stop on text OR after 20 messages --------------------

export const agent2 = new Agent({
  name: 'chatbot',
  model: llmModel,
  instructions: "Have a conversation. Say GOODBYE when you're finished.",
  termination: new TextMention('GOODBYE').or(new MaxMessage(20)),
});

// -- Example 3: AND -- stop only when BOTH conditions met ------------------

// Only terminate when the agent says "FINAL ANSWER" AND we've had
// at least 5 messages (ensuring sufficient deliberation)
export const agent3 = new Agent({
  name: 'deliberator',
  model: llmModel,
  tools: [search],
  instructions:
    'Research thoroughly. Only provide your FINAL ANSWER after ' +
    'using the search tool at least twice.',
  termination: new TextMention('FINAL ANSWER').and(new MaxMessage(5)),
});

// -- Example 4: Complex composition ----------------------------------------

// Stop when: (TERMINATE signal) OR (DONE + at least 10 messages) OR (token budget exceeded)
const complexStop = new StopMessage('TERMINATE')
  .or(new TextMention('DONE').and(new MaxMessage(10)))
  .or(new TokenUsageCondition({ maxTotalTokens: 50000 }));

export const agent4 = new Agent({
  name: 'complex_agent',
  model: llmModel,
  tools: [search],
  instructions: 'Research and provide a comprehensive answer.',
  termination: complexStop,
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent1);
    await runtime.serve(agent1);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // console.log('--- Simple text mention termination ---');
    // const result = await runtime.run(agent1, 'What are AI agents?');
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('19-composable-termination.ts') || process.argv[1]?.endsWith('19-composable-termination.js')) {
  main().catch(console.error);
}
