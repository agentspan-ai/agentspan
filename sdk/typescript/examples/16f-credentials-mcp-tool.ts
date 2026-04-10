/**
 * Credentials -- MCP tool with server-side credential resolution.
 *
 * Demonstrates:
 *   - mcpTool() with credentials: ["MCP_API_KEY"]
 *   - ${MCP_API_KEY} in headers resolved server-side before MCP calls
 *   - MCP server authentication handled transparently
 *
 * MCP Test Server Setup (mcp-testkit):
 *   pip install mcp-testkit
 *
 *   # Start with auth (to demonstrate credential resolution):
 *   mcp-testkit --transport http --auth <secret>
 *
 *   # Store credentials via CLI or Agentspan UI:
 *   agentspan credentials set MCP_API_KEY <secret>
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - mcp-testkit running on http://localhost:3001 (see setup above)
 *   - MCP_API_KEY stored via CLI or Agentspan UI
 */

import { Agent, AgentRuntime, mcpTool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// MCP tool with credential-bearing headers.
// ${MCP_API_KEY} is resolved server-side before each MCP call.
const myMcpTools = mcpTool({
  serverUrl: 'http://localhost:3001/mcp',
  headers: {
    Authorization: 'Bearer ${MCP_API_KEY}',
  },
  credentials: ['MCP_API_KEY'],
});

export const agent = new Agent({
  name: 'mcp_cred_agent',
  model: llmModel,
  tools: [myMcpTools],
  instructions: 'You have access to MCP tools. Use them to help the user.',
});

// -- Run ----------------------------------------------------------------------

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'What tools are available?');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents mcp_cred_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
