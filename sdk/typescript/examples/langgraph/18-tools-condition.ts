/**
 * tools_condition -- StateGraph using prebuilt toolsCondition for a ReAct loop.
 *
 * Demonstrates:
 *   - Building a ReAct loop using toolsCondition from @langchain/langgraph/prebuilt
 *   - toolsCondition returns "tools" if the last message has tool_calls, else END
 *   - Practical use: a weather and timezone information agent
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
const getWeatherTool = new DynamicStructuredTool({
  name: 'get_weather',
  description: 'Return current weather conditions for a city (mock data).',
  schema: z.object({
    city: z.string().describe('The name of the city to get weather for'),
  }),
  func: async ({ city }) => {
    const weatherDb: Record<string, string> = {
      london: 'Cloudy, 12C, 80% humidity, light drizzle',
      'new york': 'Sunny, 22C, 55% humidity, clear skies',
      tokyo: 'Partly cloudy, 18C, 65% humidity, mild breeze',
      sydney: 'Warm and sunny, 28C, 45% humidity',
      paris: 'Overcast, 9C, 85% humidity, foggy morning',
    };
    return weatherDb[city.toLowerCase()] ?? `Weather data unavailable for ${city}.`;
  },
});

const getTimezoneTool = new DynamicStructuredTool({
  name: 'get_timezone',
  description: 'Return the current timezone and UTC offset for a city.',
  schema: z.object({
    city: z.string().describe('The name of the city to look up'),
  }),
  func: async ({ city }) => {
    const timezoneDb: Record<string, string> = {
      london: 'GMT+0 (BST+1 in summer) — Europe/London',
      'new york': 'UTC-5 (EDT-4 in summer) — America/New_York',
      tokyo: 'UTC+9 — Asia/Tokyo',
      sydney: 'UTC+10 (AEDT+11 in summer) — Australia/Sydney',
      paris: 'UTC+1 (CEST+2 in summer) — Europe/Paris',
    };
    return timezoneDb[city.toLowerCase()] ?? `Timezone data unavailable for ${city}.`;
  },
});

// ---------------------------------------------------------------------------
// Build the graph manually (ReAct loop with ToolNode)
// ---------------------------------------------------------------------------
const tools = [getWeatherTool, getTimezoneTool];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);
const toolNode = new ToolNode(tools);

async function agent(state: typeof MessagesAnnotation.State) {
  const response = await llm.invoke(state.messages);
  return { messages: [response] };
}

// toolsCondition: if the last message has tool_calls -> "tools", else -> END
const builder = new StateGraph(MessagesAnnotation)
  .addNode('agent', agent)
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

const PROMPT =
  "What's the weather like in Tokyo and London? Also what timezone are they in?";

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('18-tools-condition.ts') || process.argv[1]?.endsWith('18-tools-condition.js')) {
  main().catch(console.error);
}
