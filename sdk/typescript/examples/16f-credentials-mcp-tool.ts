/**
 * Credentials -- MCP tool with server-side credential resolution.
 *
 * Demonstrates:
 *   - mcpTool() with credentials: ["MCP_API_KEY"]
 *   - ${MCP_API_KEY} in headers resolved server-side before MCP calls
 *   - MCP server authentication handled transparently
 *
 * Setup (one-time):
 *   agentspan credentials set --name MCP_API_KEY
 *
 * MCP Weather Server Setup:
 *   # Install and start the weather MCP server (runs on port 3001):
 *   npx -y @philschmid/weather-mcp
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - MCP server running on http://localhost:3001/mcp (see setup above)
 *   - MCP_API_KEY stored via `agentspan credentials set`
 */

import { Agent, AgentRuntime, mcpTool } from '../src/index.js';
import { llmModel } from './settings.js';

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

// Only run when executed directly (not when imported for discovery)
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

if (process.argv[1]?.endsWith('16f-credentials-mcp-tool.ts') || process.argv[1]?.endsWith('16f-credentials-mcp-tool.js')) {
  main().catch(console.error);
}
