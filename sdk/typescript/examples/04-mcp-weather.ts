/**
 * MCP Weather — using Conductor's MCP system tasks for live weather.
 *
 * Demonstrates the mcpTool() function which uses Conductor's built-in
 * LIST_MCP_TOOLS and CALL_MCP_TOOL system tasks. The MCP test server
 * provides deterministic weather data, and the Conductor server handles all
 * MCP protocol communication — no worker process needed.
 *
 * Flow:
 *   ListMcpTools -> LLM (picks tool) -> CallMcpTool -> Final LLM
 *
 * MCP Test Server Setup (mcp-testkit):
 *   pip install mcp-testkit
 *
 *   # Start without auth:
 *   mcp-testkit --transport http
 *
 *   # Or start with auth (requires storing the secret as a credential):
 *   mcp-testkit --transport http --auth <secret>
 *
 *   # Store credentials via CLI or Agentspan UI:
 *   agentspan credentials set MCP_TEST_API_KEY <secret>
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - mcp-testkit running on http://localhost:3001 (see setup above)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, mcpTool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// Create MCP tool — Conductor discovers tools from mcp-testkit at runtime
// ${MCP_TEST_API_KEY} is resolved server-side from the credential store.
const weather = mcpTool({
  serverUrl: 'http://localhost:3001/mcp',
  name: 'weather_mcp',
  description:
    'Weather and air quality tools via MCP, use it to get current and historical weather information for a city',
  headers: { Authorization: 'Bearer ${MCP_TEST_API_KEY}' },
  credentials: ['MCP_TEST_API_KEY'],
});

export const agent = new Agent({
  name: 'weather_mcp_agent',
  model: llmModel,
  maxTokens: 10240,
  tools: [weather],
  instructions:
    'You are a weather assistant. Use the available MCP tools ' +
    'to answer questions about weather conditions around the world.' +
    'when asked get the current temperature in F' +
    'use the tools provided',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    "What's the weather like in San Francisco (CA) right now?",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents weather_mcp_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
