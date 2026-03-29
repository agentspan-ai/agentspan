/**
 * ToolNode -- StateGraph with ToolNode + toolsCondition for a ReAct loop.
 *
 * Demonstrates:
 *   - Manually building a ReAct loop with StateGraph + MessagesAnnotation
 *   - Using ToolNode to execute tool calls returned by the LLM
 *   - Using toolsCondition to route between tool execution and END
 *   - Message accumulation via the messages state reducer
 */

import { StateGraph, START, MessagesAnnotation } from '@langchain/langgraph';
import { ToolNode, toolsCondition } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const capitals: Record<string, string> = {
  france: 'Paris',
  germany: 'Berlin',
  japan: 'Tokyo',
  brazil: 'Brasilia',
  australia: 'Canberra',
  india: 'New Delhi',
  usa: 'Washington D.C.',
  canada: 'Ottawa',
};

const populations: Record<string, string> = {
  france: '68 million',
  germany: '84 million',
  japan: '125 million',
  brazil: '215 million',
  australia: '26 million',
  india: '1.4 billion',
  usa: '335 million',
  canada: '38 million',
};

const lookupCapitalTool = new DynamicStructuredTool({
  name: 'lookup_capital',
  description: 'Look up the capital city of a country.',
  schema: z.object({
    country: z.string().describe('The country name'),
  }),
  func: async ({ country }) =>
    capitals[country.toLowerCase()] ?? `Capital of ${country} is not in my database.`,
});

const lookupPopulationTool = new DynamicStructuredTool({
  name: 'lookup_population',
  description: 'Look up the approximate population of a country.',
  schema: z.object({
    country: z.string().describe('The country name'),
  }),
  func: async ({ country }) =>
    populations[country.toLowerCase()] ?? `Population data for ${country} is not available.`,
});

// ---------------------------------------------------------------------------
// Build the graph manually (ReAct loop with ToolNode)
// ---------------------------------------------------------------------------
const tools = [lookupCapitalTool, lookupPopulationTool];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);
const toolNode = new ToolNode(tools);

async function callModel(state: typeof MessagesAnnotation.State) {
  const response = await llm.invoke(state.messages);
  return { messages: [response] };
}

const builder = new StateGraph(MessagesAnnotation)
  .addNode('agent', callModel)
  .addNode('tools', toolNode)
  .addEdge(START, 'agent')
  .addConditionalEdges('agent', toolsCondition)
  .addEdge('tools', 'agent');

const graph = builder.compile();

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const PROMPT = 'What is the capital and population of Japan and Brazil?';

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
    // const result = await runtime.run(graph, PROMPT);
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('05-tool-node.ts') || process.argv[1]?.endsWith('05-tool-node.js')) {
  main().catch(console.error);
}
