/**
 * MCP Weather — using Conductor's MCP system tasks for live weather.
 *
 * Demonstrates the mcpTool() function which uses Conductor's built-in
 * LIST_MCP_TOOLS and CALL_MCP_TOOL system tasks. The MCP weather server
 * provides real weather data, and the Conductor server handles all MCP
 * protocol communication — no worker process needed.
 *
 * Flow:
 *   ListMcpTools -> LLM (picks tool) -> CallMcpTool -> Final LLM
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - MCP weather server running on http://localhost:3001/mcp
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, mcpTool } from '../src/index.js';
import { llmModel } from './settings.js';

// Create MCP tool from the weather server — Conductor discovers tools at runtime
const weather = mcpTool({
  serverUrl: 'http://localhost:3001/mcp',
  name: 'weather_mcp',
  description:
    'Weather and air quality tools via MCP, use it to get current and historical weather information for a city',
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

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    agent,
    "What's the weather like in San Francisco (CA) right now?",
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('04-mcp-weather.ts') || process.argv[1]?.endsWith('04-mcp-weather.js')) {
  main().catch(console.error);
}
