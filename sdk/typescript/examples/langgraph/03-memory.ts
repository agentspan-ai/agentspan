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
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(graph);
    await runtime.serve(graph);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // graph,
    // 'My name is Bob. Tell me something interesting about my name.',
    // { sessionId: 'agentspan-session-001' },
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('03-memory.ts') || process.argv[1]?.endsWith('03-memory.js')) {
  main().catch(console.error);
}
