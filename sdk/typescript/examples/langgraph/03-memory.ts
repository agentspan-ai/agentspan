/**
 * Memory with MemorySaver -- multi-turn conversation via checkpointer.
 *
 * Demonstrates:
 *   - Attaching a MemorySaver checkpointer to createReactAgent
 *   - Using thread_id to maintain conversation state across multiple turns
 *   - How the agent remembers context from earlier messages
 */

import { MemorySaver } from '@langchain/langgraph';
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Build the graph with checkpointer
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const checkpointer = new MemorySaver();
const graph = createReactAgent({ llm, tools: [], checkpointer });

// ---------------------------------------------------------------------------
// Run multi-turn conversation
// ---------------------------------------------------------------------------
async function main() {
  const THREAD_ID = 'user-session-001';
  const config = { configurable: { thread_id: THREAD_ID } };

  // ── Path 1: Native multi-turn ──
  console.log('=== Native LangGraph multi-turn ===');

  console.log('\n--- Turn 1: Introduce a name ---');
  const r1 = await graph.invoke(
    { messages: [new HumanMessage('My name is Alice. Please remember that.')] },
    config,
  );
  console.log('Response:', r1.messages[r1.messages.length - 1].content);

  console.log('\n--- Turn 2: Ask the agent to recall ---');
  const r2 = await graph.invoke(
    { messages: [new HumanMessage('What is my name?')] },
    config,
  );
  console.log('Response:', r2.messages[r2.messages.length - 1].content);

  console.log('\n--- Turn 3: Continue the conversation ---');
  const r3 = await graph.invoke(
    { messages: [new HumanMessage('Tell me a fun fact about the name Alice.')] },
    config,
  );
  console.log('Response:', r3.messages[r3.messages.length - 1].content);

  // ── Path 2: Agentspan passthrough (single turn, no server-side memory) ──
  console.log('\n=== Agentspan passthrough execution (single turn) ===');
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      graph,
      'My name is Bob. Tell me something interesting about my name.',
      { sessionId: 'agentspan-session-001' },
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
