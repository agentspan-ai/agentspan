// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// MCP Weather — using Conductor's MCP system tasks for live weather.
//
// Demonstrates McpTools.Create() which uses Conductor's built-in
// LIST_MCP_TOOLS and CALL_MCP_TOOL system tasks. The MCP test server
// provides deterministic weather data, and the Conductor server handles
// all MCP protocol communication — no worker process needed.
//
// Flow:
//   ListMcpTools → LLM (picks tool) → CallMcpTool → Final LLM
//
// MCP Test Server Setup (mcp-testkit):
//   pip install mcp-testkit
//
//   # Start without auth:
//   mcp-testkit --transport http
//
//   # Or start with auth:
//   mcp-testkit --transport http --auth <secret>
//   agentspan credentials set MCP_TEST_API_KEY <secret>
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - mcp-testkit running on http://localhost:3001 (see above)
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// MCP tool — Conductor discovers tools from mcp-testkit at runtime.
// ${MCP_TEST_API_KEY} is resolved server-side from the credential store.
var weather = McpTools.Create(
    serverUrl:   "http://localhost:3001/mcp",
    name:        "weather_mcp",
    description: "Weather and air quality tools via MCP. Use it to get current and historical weather information for a city.",
    headers:     new Dictionary<string, string>
    {
        ["Authorization"] = "Bearer ${MCP_TEST_API_KEY}",
    },
    credentials: ["MCP_TEST_API_KEY"]);

var agent = new Agent("weather_mcp_agent")
{
    Model        = Settings.LlmModel,
    MaxTokens    = 10240,
    Tools        = [weather],
    Instructions =
        "You are a weather assistant. Use the available MCP tools " +
        "to answer questions about weather conditions around the world. " +
        "When asked, get the current temperature in °F. Use the tools provided.",
};

Console.WriteLine("=== MCP Weather Demo ===");
await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What's the weather like in San Francisco (CA) right now?");
result.PrintResult();
