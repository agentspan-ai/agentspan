/**
 * LangChain — Agent Executor
 *
 * Demonstrates passing a LangChain AgentExecutor to runtime.run().
 * The SDK auto-detects the framework and uses the passthrough worker pattern.
 */

import { AgentRuntime } from '../../src/index.js';

// -- Mock a LangChain AgentExecutor --
// In production, this would be:
//   import { AgentExecutor, createOpenAIFunctionsAgent } from 'langchain/agents';
//   const executor = AgentExecutor.fromAgentAndTools({ agent, tools });
const langChainExecutor = {
  // LangChain AgentExecutor has invoke/call
  invoke: async (input: Record<string, unknown>) => {
    return {
      output: `LangChain response to: ${input.input ?? input.prompt}`,
    };
  },
  // LangChain agents expose these properties
  agent: {
    llmChain: { llm: { modelName: 'gpt-4o' } },
  },
  tools: [
    { name: 'search', description: 'Search the web' },
  ],
  name: 'langchain_agent_executor',
};

async function main() {
  const runtime = new AgentRuntime();

  // The runtime detects LangChain format (has invoke + agent + tools)
  // and wraps it in a passthrough worker.
  console.log('Running LangChain agent via Agentspan...');
  const result = await runtime.run(langChainExecutor, 'What are the latest AI trends?');
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
