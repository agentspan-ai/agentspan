/**
 * Tool Call Chain -- chaining multiple tool calls in sequence.
 *
 * Demonstrates:
 *   - An agent that must call several tools in a defined order
 *   - Using ToolNode and toolsCondition for standard LangGraph tool loop
 *   - State accumulation across multiple tool invocations
 *   - Practical use case: data enrichment pipeline (fetch -> transform -> validate -> summarize)
 */

import { StateGraph, START, MessagesAnnotation } from '@langchain/langgraph';
import { ToolNode, toolsCondition } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { SystemMessage } from '@langchain/core/messages';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const fetchCompanyInfoTool = new DynamicStructuredTool({
  name: 'fetch_company_info',
  description: 'Look up basic information about a company.',
  schema: z.object({
    company_name: z.string().describe('The company name to look up'),
  }),
  func: async ({ company_name }) => {
    const data: Record<string, object> = {
      openai: { founded: 2015, employees: '~1500', sector: 'AI Research' },
      google: { founded: 1998, employees: '~190000', sector: 'Technology' },
      microsoft: { founded: 1975, employees: '~220000', sector: 'Technology' },
      anthropic: { founded: 2021, employees: '~500', sector: 'AI Safety' },
    };
    const key = company_name.toLowerCase();
    if (key in data) {
      return JSON.stringify(data[key]);
    }
    return JSON.stringify({ error: `Company '${company_name}' not found in database` });
  },
});

const calculateCompanyAgeTool = new DynamicStructuredTool({
  name: 'calculate_company_age',
  description: 'Calculate how many years a company has been in operation.',
  schema: z.object({
    founded_year: z.number().describe('The year the company was founded'),
  }),
  func: async ({ founded_year }) => {
    const currentYear = 2025;
    const age = currentYear - founded_year;
    return `The company has been operating for ${age} years (founded ${founded_year})`;
  },
});

const getSectorPeersTool = new DynamicStructuredTool({
  name: 'get_sector_peers',
  description: 'Return a list of well-known companies in the same sector.',
  schema: z.object({
    sector: z.string().describe('The sector to find peers for'),
  }),
  func: async ({ sector }) => {
    const peers: Record<string, string[]> = {
      'ai research': ['OpenAI', 'Anthropic', 'DeepMind', 'Cohere'],
      'ai safety': ['Anthropic', 'OpenAI', 'Redwood Research'],
      technology: ['Apple', 'Microsoft', 'Google', 'Meta', 'Amazon'],
    };
    const key = sector.toLowerCase();
    if (key in peers) {
      return `Peers in '${sector}': ${peers[key].join(', ')}`;
    }
    return `No peer data available for sector: ${sector}`;
  },
});

const generateInvestmentNoteTool = new DynamicStructuredTool({
  name: 'generate_investment_note',
  description: 'Generate a brief investment note combining company facts.',
  schema: z.object({
    company: z.string().describe('Company name'),
    age: z.string().describe('Operational history info'),
    peers: z.string().describe('Competitive landscape info'),
  }),
  func: async ({ company, age, peers }) => {
    return (
      `Investment Note — ${company}\n` +
      `Operational history: ${age}\n` +
      `Competitive landscape: ${peers}\n` +
      `Recommendation: Review financials and recent growth metrics before investing.`
    );
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const tools = [
  fetchCompanyInfoTool,
  calculateCompanyAgeTool,
  getSectorPeersTool,
  generateInvestmentNoteTool,
];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);
const toolNode = new ToolNode(tools);

async function agent(state: typeof MessagesAnnotation.State) {
  const system = new SystemMessage(
    'You are a financial analyst. For each company query, you MUST:\n' +
      '1. Fetch company info\n' +
      '2. Calculate company age using the founded year\n' +
      '3. Get sector peers\n' +
      '4. Generate an investment note combining all facts\n' +
      'Call the tools in this order.',
  );
  const messages = [system, ...state.messages];
  const response = await llm.invoke(messages);
  return { messages: [response] };
}

const builder = new StateGraph(MessagesAnnotation)
  .addNode('agent', agent)
  .addNode('tools', toolNode)
  .addEdge(START, 'agent')
  .addConditionalEdges('agent', toolsCondition)
  .addEdge('tools', 'agent');

const graph = builder.compile();

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
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
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    const result = await runtime.run(graph, 'Analyze Anthropic for investment purposes.');
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('39-tool-call-chain.ts') || process.argv[1]?.endsWith('39-tool-call-chain.js')) {
  main().catch(console.error);
}
