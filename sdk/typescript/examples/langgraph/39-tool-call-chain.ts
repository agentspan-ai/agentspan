/**
 * Tool Call Chain -- chaining multiple tool calls in sequence.
 *
 * Demonstrates:
 *   - An agent that must call several tools in a defined order
 *   - Using ToolNode and tools_condition for standard LangGraph tool loop
 *   - State accumulation across multiple tool invocations
 *   - Practical use case: data enrichment pipeline (fetch -> transform -> validate)
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   import { ToolNode, toolsCondition } from '@langchain/langgraph/prebuilt';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------
const COMPANY_DATA: Record<string, { founded: number; employees: string; sector: string }> = {
  openai: { founded: 2015, employees: '~1500', sector: 'AI Research' },
  google: { founded: 1998, employees: '~190000', sector: 'Technology' },
  microsoft: { founded: 1975, employees: '~220000', sector: 'Technology' },
  anthropic: { founded: 2021, employees: '~500', sector: 'AI Safety' },
};

function fetchCompanyInfo(companyName: string): string {
  const data = COMPANY_DATA[companyName.toLowerCase()];
  if (data) return JSON.stringify(data);
  return JSON.stringify({ error: `Company '${companyName}' not found in database` });
}

function calculateCompanyAge(foundedYear: number): string {
  const age = 2025 - foundedYear;
  return `The company has been operating for ${age} years (founded ${foundedYear})`;
}

function getSectorPeers(sector: string): string {
  const peers: Record<string, string[]> = {
    'ai research': ['OpenAI', 'Anthropic', 'DeepMind', 'Cohere'],
    'ai safety': ['Anthropic', 'OpenAI', 'Redwood Research'],
    technology: ['Apple', 'Microsoft', 'Google', 'Meta', 'Amazon'],
  };
  const found = peers[sector.toLowerCase()];
  if (found) return `Peers in '${sector}': ${found.join(', ')}`;
  return `No peer data available for sector: ${sector}`;
}

function generateInvestmentNote(company: string, age: string, peers: string): string {
  return (
    `Investment Note -- ${company}\n` +
    `Operational history: ${age}\n` +
    `Competitive landscape: ${peers}\n` +
    `Recommendation: Review financials and recent growth metrics before investing.`
  );
}

// ---------------------------------------------------------------------------
// Mock compiled graph (simulates multi-step tool calls)
// ---------------------------------------------------------------------------
const graph = {
  name: 'tool_call_chain_agent',

  invoke: async (input: Record<string, unknown>) => {
    const query = (input.input as string) ?? '';

    // Extract company name from query
    const companyMatch = query.match(/\b(anthropic|openai|google|microsoft)\b/i);
    const company = companyMatch?.[1] ?? 'Anthropic';

    // Step 1: Fetch company info
    const info = fetchCompanyInfo(company);
    const parsed = JSON.parse(info);

    // Step 2: Calculate age
    const age = calculateCompanyAge(parsed.founded);

    // Step 3: Get sector peers
    const peers = getSectorPeers(parsed.sector);

    // Step 4: Generate investment note
    const note = generateInvestmentNote(company, age, peers);

    return {
      messages: [
        { role: 'user', content: query },
        { role: 'assistant', content: note },
      ],
    };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['agent', {}],
      ['tools', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'agent'],
      ['agent', 'tools'],
      ['tools', 'agent'],
      ['agent', '__end__'],
    ],
  }),

  nodes: new Map([
    ['agent', {}],
    ['tools', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const query = (input.input as string) ?? '';
    const companyMatch = query.match(/\b(anthropic|openai|google|microsoft)\b/i);
    const company = companyMatch?.[1] ?? 'Anthropic';

    const info = fetchCompanyInfo(company);
    yield ['updates', { tools: { tool: 'fetch_company_info', result: info } }];

    const parsed = JSON.parse(info);
    const age = calculateCompanyAge(parsed.founded);
    yield ['updates', { tools: { tool: 'calculate_company_age', result: age } }];

    const peers = getSectorPeers(parsed.sector);
    yield ['updates', { tools: { tool: 'get_sector_peers', result: peers } }];

    const note = generateInvestmentNote(company, age, peers);
    yield ['updates', { agent: { messages: [{ role: 'assistant', content: note }] } }];
    yield ['values', { messages: [{ role: 'assistant', content: note }] }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      graph,
      'Analyze Anthropic for investment purposes.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
