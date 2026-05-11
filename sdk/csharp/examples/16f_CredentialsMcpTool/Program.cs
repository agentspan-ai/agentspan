// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Credentials — MCP tool with server-side credential resolution.
//
// Demonstrates:
//   - McpTools.Create() with credentials: ["MCP_API_KEY"]
//   - ${MCP_API_KEY} in headers resolved server-side before MCP calls
//   - MCP server authentication handled transparently — the C# process
//     never sees the plaintext secret
//
// MCP Test Server Setup (mcp-testkit):
//   pip install mcp-testkit
//
//   # Start with auth (to demonstrate credential resolution):
//   mcp-testkit --transport http --auth <secret>
//
//   # Store credentials via CLI or Agentspan UI:
//   agentspan credentials set MCP_API_KEY <secret>
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment
//   - mcp-testkit running on http://localhost:3001 (see above)
//   - MCP_API_KEY stored via `agentspan credentials set`

using Agentspan;
using Agentspan.Examples;

// MCP tool with credential-bearing headers.
// ${MCP_API_KEY} is resolved server-side from the credential store
// before each MCP call — the plaintext value never appears in code.
var mcpTools = McpTools.Create(
    serverUrl:   "http://localhost:3001/mcp",
    headers:     new Dictionary<string, string>
    {
        ["Authorization"] = "Bearer ${MCP_API_KEY}",
    },
    credentials: ["MCP_API_KEY"]);

var agent = new Agent("mcp_cred_agent")
{
    Model        = Settings.LlmModel,
    Tools        = [mcpTools],
    Instructions = "You have access to MCP tools. Use them to help the user.",
};

Console.WriteLine("=== MCP Tool with Credential Resolution ===");
await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What tools are available?");
result.PrintResult();
