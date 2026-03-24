/**
 * Hello World -- simplest LangGraph agent with no tools.
 *
 * Demonstrates:
 *   - Using createReactAgent from @langchain/langgraph/prebuilt
 *   - Running a graph via Agentspan runtime.run() passthrough
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({ llm, tools: [] });

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'Say hello and tell me a fun fact about Python programming.';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
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
