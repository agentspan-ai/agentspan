/**
 * Memory with MemorySaver -- multi-turn conversation via checkpointer.
 *
 * Demonstrates:
 *   - Attaching a MemorySaver checkpointer to createReactAgent
 *   - Running via Agentspan passthrough (single turn)
 *   - How the agent remembers context from earlier messages
 */

import { MemorySaver } from '@langchain/langgraph';
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Build the graph with checkpointer
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const checkpointer = new MemorySaver();
const graph = createReactAgent({ llm, tools: [], checkpointer });

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
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
