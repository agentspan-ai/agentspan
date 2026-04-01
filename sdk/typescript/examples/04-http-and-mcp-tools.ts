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
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool, httpTool, mcpTool } from '../src/index.js';
import { llmModel } from './settings.js';

// TypeScript tool (needs a worker)
const formatReport = tool(
  async (args: { data: Record<string, unknown> }) => {
    return `Report: ${JSON.stringify(args.data)}`;
  },
  {
    name: 'format_report',
    description: 'Format raw data into a readable report.',
    inputSchema: z.object({
      data: z.record(z.unknown()).describe('The data to format into a report'),
    }),
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
    const result = await runtime.run(agent, 'Get the weather in London and format it as a report.');
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('04-http-and-mcp-tools.ts') || process.argv[1]?.endsWith('04-http-and-mcp-tools.js')) {
  main().catch(console.error);
}
