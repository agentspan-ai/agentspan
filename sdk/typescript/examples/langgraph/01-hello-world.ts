/**
 * Hello World -- simplest LangGraph agent with no tools.
 *
 * Demonstrates:
 *   - Using createReactAgent from @langchain/langgraph/prebuilt
 *   - Running a graph natively via graph.invoke()
 *   - Running a graph via Agentspan runtime.run() passthrough
 *   - Comparing both results
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({ llm, tools: [] });

const PROMPT = 'Say hello and tell me a fun fact about Python programming.';

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  // ── Path 1: Native LangGraph execution ──
  console.log('=== Native LangGraph execution ===');
  const nativeResult = await graph.invoke({
    messages: [new HumanMessage(PROMPT)],
  });
  const lastNativeMsg = nativeResult.messages[nativeResult.messages.length - 1];
  console.log('Native result:', lastNativeMsg.content);

  // ── Path 2: Agentspan passthrough ──
  console.log('\n=== Agentspan passthrough execution ===');
  const runtime = new AgentRuntime();
  try {
    const agentspanResult = await runtime.run(graph, PROMPT);
    console.log('Status:', agentspanResult.status);
    agentspanResult.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
