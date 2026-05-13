/**
 * 71 - API Tool — auto-discover endpoints from OpenAPI, Swagger, or Postman specs.
 *
 * Demonstrates apiTool(), which points to an API spec and automatically
 * discovers all operations as agent tools. No manual tool definitions needed.
 *
 * Four patterns shown:
 *   1. OpenAPI 3.x spec URL (local MCP test server with 65 deterministic tools)
 *   2. Filtered operations — whitelist specific endpoints via toolNames
 *   3. Mixing apiTool with other tool types
 *   4. Large API with credential auth (GitHub)
 *
 * MCP Test Server Setup (mcp-testkit) — required for examples 1-3:
 *   pip install mcp-testkit
 *
 *   # Start without auth:
 *   mcp-testkit --transport http
 *
 *   # Or start with auth (requires storing the secret as a credential):
 *   mcp-testkit --transport http --auth <secret>
 *
 *   # Store credentials via CLI or Agentspan UI:
 *   agentspan credentials set HTTP_TEST_API_KEY <secret>
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 *   - mcp-testkit running on http://localhost:3001 (for examples 1-3, see setup above)
 *   - For GitHub example: agentspan credentials set GITHUB_TOKEN ghp_xxx
 */

import { Agent, AgentRuntime, apiTool, tool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

const MCP_TEST_SERVER_SPEC = 'http://localhost:3001/api-docs';

// -- Example 1: OpenAPI spec (full discovery) --------------------------------

const mathApi = apiTool({
  url: MCP_TEST_SERVER_SPEC,
  name: 'mcp_test_tools',
  headers: { Authorization: 'Bearer ${HTTP_TEST_API_KEY}' },
  credentials: ['HTTP_TEST_API_KEY'],
  maxTools: 10, // 65 ops — filter to top 10 most relevant
});

export const mathAgent = new Agent({
  name: 'math_assistant',
  model: llmModel,
  instructions: 'You are a math assistant. Use the API tools to compute results.',
  tools: [mathApi],
});

// -- Example 2: Filtered operations (toolNames whitelist) --------------------

const stringApi = apiTool({
  url: MCP_TEST_SERVER_SPEC,
  headers: { Authorization: 'Bearer ${HTTP_TEST_API_KEY}' },
  credentials: ['HTTP_TEST_API_KEY'],
  toolNames: ['string_reverse', 'string_uppercase', 'string_length'],
});

export const stringAgent = new Agent({
  name: 'string_assistant',
  model: llmModel,
  instructions: 'You are a string manipulation assistant.',
  tools: [stringApi],
});

// -- Example 3: Mix apiTool with other tool types ----------------------------

const calculate = tool(
  async (args: { expression: string }) => {
    const safeBuiltins: Record<string, (...a: number[]) => number> = {
      abs: Math.abs,
      round: Math.round,
      sqrt: Math.sqrt,
      pow: Math.pow,
    };
    try {
      const fn = new Function(...Object.keys(safeBuiltins), `return (${args.expression});`);
      return { expression: args.expression, result: fn(...Object.values(safeBuiltins)) };
    } catch (e) {
      return { expression: args.expression, error: String(e) };
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a math expression.',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'A mathematical expression' },
      },
      required: ['expression'],
    },
  },
);

const collectionApi = apiTool({
  url: MCP_TEST_SERVER_SPEC,
  headers: { Authorization: 'Bearer ${HTTP_TEST_API_KEY}' },
  credentials: ['HTTP_TEST_API_KEY'],
  toolNames: ['collection_sort', 'collection_unique', 'collection_flatten'],
  maxTools: 10,
});

export const multiToolAgent = new Agent({
  name: 'multi_tool_assistant',
  model: llmModel,
  instructions:
    'You are a versatile assistant. Use API tools for collection operations, ' +
    'and the calculator for math. Pick the best tool for each request.',
  tools: [collectionApi, calculate],
});

// -- Example 4: Large API with credential auth -------------------------------

const github = apiTool({
  url: 'https://api.github.com',
  headers: {
    Authorization: 'token ${GITHUB_TOKEN}',
    Accept: 'application/vnd.github+json',
  },
  credentials: ['GITHUB_TOKEN'],
  toolNames: [
    'repos_list_for_user',
    'repos_create_for_authenticated_user',
    'issues_list_for_repo',
    'issues_create',
  ],
  maxTools: 20,
});

export const githubAgent = new Agent({
  name: 'github_assistant',
  model: llmModel,
  instructions: 'You help users manage their GitHub repositories and issues.',
  tools: [github],
});

// -- Run ---------------------------------------------------------------------

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Example 1: Math via OpenAPI-discovered tools
    console.log('=== Math API ===');
    const result = await runtime.run(mathAgent, 'What is 15 + 27? Also compute 8 factorial.');
    result.printResult();

    // Example 2: Filtered string tools
    console.log('\n=== String API (filtered) ===');
    const result2 = await runtime.run(
      stringAgent,
      "Reverse the string 'hello world' and tell me its length.",
    );
    result2.printResult();

    // Example 3: Mixed tools
    console.log('\n=== Mixed Tools ===');
    const result3 = await runtime.run(
      multiToolAgent,
      'Sort [3,1,4,1,5,9] and also compute sqrt(144).',
    );
    result3.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(mathAgent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents math_assistant
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(mathAgent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
