/**
 * LangGraph — React Agent
 *
 * Demonstrates passing a LangGraph compiled graph to runtime.run().
 * The SDK auto-detects the framework and uses the passthrough worker pattern.
 */

import { AgentRuntime } from '../../src/index.js';

// -- Mock a LangGraph compiled graph --
// In production, this would be a real LangGraph CompiledGraph:
//   import { createReactAgent } from '@langchain/langgraph/prebuilt';
//   const graph = createReactAgent({ model, tools });
const langGraphAgent = {
  // LangGraph compiled graphs have an invoke method
  invoke: async (input: Record<string, unknown>) => {
    return {
      messages: [
        { role: 'assistant', content: `LangGraph response to: ${input.prompt ?? input.messages}` },
      ],
    };
  },
  // LangGraph graphs expose a getGraph() method
  getGraph: () => ({
    nodes: ['agent', 'tools'],
    edges: [['agent', 'tools'], ['tools', 'agent']],
  }),
  name: 'langgraph_react_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  // The runtime detects LangGraph format (has invoke + getGraph)
  // and wraps it in a passthrough worker.
  console.log('Running LangGraph agent via Agentspan...');
  const result = await runtime.run(langGraphAgent, 'Explain quantum entanglement.');
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
