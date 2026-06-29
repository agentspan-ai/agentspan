/**
 * 08 - Credentials
 *
 * Demonstrates credential management:
 * - Tool that declares credentials and reads them with getCredential()
 * - httpTool with ${CREDENTIAL} header substitution
 */

import {
  Agent,
  AgentRuntime,
  tool,
  httpTool,
  getCredential,
} from '@conductor-oss/conductor-agent-sdk';
import type { ToolContext } from '@conductor-oss/conductor-agent-sdk';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Tool that declares a credential and reads it at runtime --
const dbLookup = tool(
  async (args: { query: string }, ctx?: ToolContext) => {
    let apiKey: string;
    try {
      apiKey = await getCredential('DB_API_KEY');
    } catch {
      apiKey = '';
    }
    return {
      query: args.query,
      session: ctx?.sessionId ?? 'unknown',
      keyPresent: apiKey !== '',
    };
  },
  {
    name: 'db_lookup',
    description: 'Query the research database.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string' },
      },
      required: ['query'],
    },
    credentials: ['DB_API_KEY'],
  },
);

// -- Another tool reading a credential at runtime --
const analyticsTool = tool(
  async (args: { topic: string }) => {
    let key: string;
    try {
      key = await getCredential('ANALYTICS_KEY');
    } catch {
      key = 'unavailable';
    }
    return { topic: args.topic, keyPresent: key !== 'unavailable' };
  },
  {
    name: 'analytics',
    description: 'Fetch analytics data.',
    inputSchema: {
      type: 'object',
      properties: {
        topic: { type: 'string' },
      },
      required: ['topic'],
    },
    credentials: ['ANALYTICS_KEY'],
  },
);

// -- HTTP tool with header credential substitution --
const searchApi = httpTool({
  name: 'search_api',
  description: 'Search external API with authentication.',
  url: 'https://api.example.com/search',
  method: 'GET',
  headers: {
    'Authorization': 'Bearer ${SEARCH_API_KEY}',
    'X-Org-Id': '${ORG_ID}',
  },
  inputSchema: {
    type: 'object',
    properties: { q: { type: 'string' } },
    required: ['q'],
  },
  credentials: ['SEARCH_API_KEY', 'ORG_ID'],
});

// -- Agent using all credential patterns --
export const agent = new Agent({
  name: 'credentialed_agent',
  model: MODEL,
  instructions: 'Use tools to research topics. All tools have proper credentials.',
  tools: [dbLookup, analyticsTool, searchApi],
  credentials: ['SEARCH_API_KEY', 'DB_API_KEY', 'ANALYTICS_KEY', 'ORG_ID'],
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Research quantum computing trends.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents credentialed_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
