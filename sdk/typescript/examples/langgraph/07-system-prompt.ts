/**
 * System Prompt -- createReactAgent with a detailed persona via prompt option.
 *
 * Demonstrates:
 *   - Using the prompt parameter on createReactAgent to set a system prompt
 *   - Creating a specialized persona (Socratic tutor)
 *   - How the system prompt shapes all LLM responses
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// System prompt (Socratic tutor persona)
// ---------------------------------------------------------------------------
const TUTOR_SYSTEM_PROMPT = `You are Socrates, an ancient Greek philosopher and skilled tutor.

Your teaching style:
- Never give direct answers; instead guide students through questions
- Use the Socratic method: ask probing questions that lead to insight
- When a student is close to an answer, acknowledge their progress
- Celebrate intellectual curiosity
- Use analogies from everyday ancient Greek life when helpful
- Speak with wisdom and calm, occasionally referencing your own experiences

Remember: your goal is to help the student discover the answer themselves,
not to provide it for them.`;

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0.7 });
const graph = createReactAgent({
  llm,
  tools: [],
  prompt: new SystemMessage(TUTOR_SYSTEM_PROMPT),
});

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  instructions: TUTOR_SYSTEM_PROMPT,
  framework: 'langgraph',
};

const PROMPT = 'I want to understand why 1 + 1 = 2. Can you just tell me?';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('07-system-prompt.ts') || process.argv[1]?.endsWith('07-system-prompt.js')) {
  main().catch(console.error);
}
