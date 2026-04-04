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
 * MCP Weather Server Setup:
 *   # Install and start the weather MCP server (runs on port 3001):
 *   npx -y @philschmid/weather-mcp
 *
 *   # Verify it's running:
 *   curl http://localhost:3001/mcp
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - MCP weather server running on http://localhost:3001/mcp (see setup above)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, tool, httpTool, mcpTool } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// TypeScript tool (needs a worker)
const formatReport = tool(
  async (args: { data: Record<string, unknown> }) => {
    return `Report: ${JSON.stringify(args.data)}`;
  },
  {
    name: 'format_report',
    description: 'Format raw data into a readable report.',
    inputSchema: {
      type: 'object',
      properties: {
        data: { type: 'object', additionalProperties: true, description: 'The data to format into a report' },
      },
      required: ['data'],
    },
  },
);

// HTTP tool (pure server-side, no worker needed)
const weatherApi = httpTool({
  name: 'get_current_weather',
  description: 'Get current weather for a city from the weather API',
  url: 'http://localhost:3001/mcp',
  method: 'POST',
  accept: ['text/event-stream', 'application/json'],
  inputSchema: {
    type: 'object',
    properties: {
      jsonrpc: {
        type: 'string',
        const: '2.0',
        },
      id: {
        const: 1,
        },
      method: {
        type: 'string',
        const: 'tools/call',
        },
      params: {
        type: 'object',
        additionalProperties: false,
        properties: {
          name: {
            type: 'string',
            const: 'get_current_weather',
            },
          arguments: {
            type: 'object',
            additionalProperties: false,
            properties: {
              city: {
                type: 'string',
                },
            },
            required: ['city'],
            },
        },
        required: ['name', 'arguments'],
        },
    },
    required: ['jsonrpc', 'id', 'method', 'params'],
  },
});

// MCP tools (discovered from MCP server at runtime)
const githubTools = mcpTool({
  serverUrl: 'http://localhost:3001/mcp',
  name: 'github',
  description: 'GitHub operations via MCP',
});

export const agent = new Agent({
  name: 'api_assistant',
  model: llmModel,
  tools: [formatReport, weatherApi],
  maxTokens: 102040,
  instructions: 'You have access to weather data, GitHub, and report formatting.',
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Get the weather in London and format it as a report.');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents api_assistant
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
