/**
 * 08 - Credentials
 *
 * Demonstrates credential management:
 * - Tool with credentials (isolated mode: env vars)
 * - httpTool with ${CREDENTIAL} header substitution
 * - In-process mode with getCredential()
 */

import {
  Agent,
  AgentRuntime,
  tool,
  httpTool,
  getCredential,
} from '../src/index.js';
import type { ToolContext } from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Tool with isolated credentials (env var injection) --
const dbLookup = tool(
  async (args: { query: string }, ctx?: ToolContext) => {
    // In isolated mode, credential is available as process.env.DB_API_KEY
    const apiKey = process.env.DB_API_KEY ?? 'not-set';
    return {
      query: args.query,
      session: ctx?.sessionId ?? 'unknown',
      keyPresent: apiKey !== 'not-set',
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
    credentials: [{ envVar: 'DB_API_KEY' }],
  },
);

// -- Tool with in-process credential access --
const analyticsTool = tool(
  async (args: { topic: string }) => {
    // In-process mode: use getCredential() to fetch at runtime
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
    isolated: false,
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
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(agent, 'Research quantum computing trends.');
    // result.printResult();
    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('08-credentials.ts') || process.argv[1]?.endsWith('08-credentials.js')) {

  main().catch(console.error);
}
