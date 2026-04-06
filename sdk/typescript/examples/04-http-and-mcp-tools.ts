/**
 * HTTP and MCP Tools — server-side tools (no workers needed).
 *
 * Demonstrates:
 *   - httpTool: HTTP endpoints as tools (Conductor HttpTask)
 *   - mcpTool: MCP server tools (Conductor ListMcpTools + CallMcpTool)
 *   - Mixing TypeScript tools with server-side tools
 *
 * These tools execute entirely server-side — no TypeScript worker process needed.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - MCP test server running on http://localhost:3001 (see tests/e2e/mcp-test-server)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool, httpTool, mcpTool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// TypeScript tool (needs a worker)
const formatReport = tool(
  async (args: { title: string; body: string }) => {
    return {
      report: `=== ${args.title} ===\n${args.body}\n${'='.repeat(args.title.length + 8)}`,
    };
  },
  {
    name: 'format_report',
    description: 'Format a title and body into a structured report.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Report title' },
        body: { type: 'string', description: 'Report body content' },
      },
      required: ['title', 'body'],
    },
  },
);

// HTTP tool (pure server-side, no worker needed)
// ${HTTP_TEST_API_KEY} is resolved server-side from the credential store.
// Store it with: agentspan credentials set --name HTTP_TEST_API_KEY
const reverseApi = httpTool({
  name: 'reverse_string',
  description: 'Reverse a string using the HTTP API',
  url: 'http://localhost:3001/api/string/reverse',
  method: 'POST',
  headers: { Authorization: 'Bearer ${HTTP_TEST_API_KEY}' },
  credentials: ['HTTP_TEST_API_KEY'],
  inputSchema: {
    type: 'object',
    properties: {
      text: { type: 'string', description: 'Text to reverse' },
    },
    required: ['text'],
  },
});

// MCP tools (discovered from MCP server at runtime)
// ${MCP_TEST_API_KEY} is resolved server-side from the credential store.
// Store it with: agentspan credentials set --name MCP_TEST_API_KEY
const mcpTestTools = mcpTool({
  serverUrl: 'http://localhost:3001/mcp',
  name: 'mcp_test_tools',
  description:
    'Deterministic test tools via MCP — math, string, collection, encoding, hash, datetime, validation, and conversion operations.',
  headers: { Authorization: 'Bearer ${MCP_TEST_API_KEY}' },
  credentials: ['MCP_TEST_API_KEY'],
});

export const agent = new Agent({
  name: 'http_tools_demo',
  model: llmModel,
  tools: [formatReport, reverseApi, mcpTestTools],
  instructions:
    'You can reverse strings and format reports. ' +
    'When asked to reverse a string, use reverse_string first, then format_report with the result.',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      "Reverse the string 'hello world' and add 33 and 21 append the result to that string, then write a report with the result.",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents http_tools_demo
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
