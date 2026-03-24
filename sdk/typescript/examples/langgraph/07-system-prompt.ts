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
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
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

const PROMPT = 'I want to understand why 1 + 1 = 2. Can you just tell me?';

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  // ── Path 1: Native ──
  console.log('=== Native LangGraph execution ===');
  const nativeResult = await graph.invoke({
    messages: [new HumanMessage(PROMPT)],
  });
  const lastMsg = nativeResult.messages[nativeResult.messages.length - 1];
  console.log('Socrates says:', lastMsg.content);

  // ── Path 2: Agentspan ──
  console.log('\n=== Agentspan passthrough execution ===');
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
