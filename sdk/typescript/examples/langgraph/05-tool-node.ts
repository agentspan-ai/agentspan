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
import { HumanMessage } from '@langchain/core/messages';
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

const PROMPT = 'What is the capital and population of Japan and Brazil?';

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  // ── Path 1: Native ──
  console.log('=== Native LangGraph execution ===');
  const nativeResult = await graph.invoke({
    messages: [new HumanMessage(PROMPT)],
  });
  for (const msg of nativeResult.messages) {
    const role = msg.constructor.name;
    if (msg.tool_calls && msg.tool_calls.length > 0) {
      console.log(`  ${role}: [tool_calls]`, msg.tool_calls.map((tc: any) => tc.name));
    } else {
      const content = typeof msg.content === 'string' ? msg.content.slice(0, 200) : JSON.stringify(msg.content);
      console.log(`  ${role}: ${content}`);
    }
  }

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
