// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// HTTP and MCP Tools — server-side tools (no worker process needed).
//
// Demonstrates:
//   - HttpTools.Create(): HTTP endpoints as tools (Conductor HttpTask)
//   - McpTools.Create(): MCP server tools (Conductor ListMcpTools + CallMcpTool)
//   - Mixing server-side tools with local worker tools
//
// These tools execute entirely server-side — no C# worker process is needed.
// ${...} placeholders in headers are resolved from the credential store
// by the server at execution time.
//
// MCP Test Server Setup (mcp-testkit):
//   pip install mcp-testkit
//
//   # Start without auth:
//   mcp-testkit --transport http
//
//   # Or start with auth (requires storing the secret as a credential):
//   mcp-testkit --transport http --auth <secret>
//   agentspan credentials set HTTP_TEST_API_KEY <secret>
//   agentspan credentials set MCP_TEST_API_KEY <secret>
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - mcp-testkit running on http://localhost:3001 (see above)
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.Examples;

// ── Local worker tool ─────────────────────────────────────────────────
// Runs in this process — needs the runtime's worker loop to be active.

var localTools = ToolRegistry.FromInstance(new ReportFormatter());

// ── HTTP tool (server-side, no local worker) ──────────────────────────
// The Conductor server calls the URL directly.
// ${HTTP_TEST_API_KEY} is substituted server-side from the credential store.

var reverseApi = HttpTools.Create(
    name:        "reverse_string",
    description: "Reverse a string using the HTTP API",
    url:         "http://localhost:3001/api/string/reverse",
    method:      "POST",
    headers:     new Dictionary<string, string>
    {
        ["Authorization"] = "Bearer ${HTTP_TEST_API_KEY}",
    },
    inputSchema: new JsonObject
    {
        ["type"] = "object",
        ["properties"] = new JsonObject
        {
            ["text"] = new JsonObject
            {
                ["type"]        = "string",
                ["description"] = "Text to reverse",
            },
        },
        ["required"] = new JsonArray { "text" },
    },
    credentials: ["HTTP_TEST_API_KEY"]);

// ── MCP tool (server-side, no local worker) ───────────────────────────
// Conductor discovers tools from the MCP server at runtime via
// LIST_MCP_TOOLS, then calls them via CALL_MCP_TOOL.
// ${MCP_TEST_API_KEY} is substituted server-side from the credential store.

var mcpTestTools = McpTools.Create(
    serverUrl:   "http://localhost:3001/mcp",
    name:        "mcp_test_tools",
    description: "Deterministic test tools via MCP — math, string, collection, encoding, hash, datetime, validation, and conversion operations.",
    headers:     new Dictionary<string, string>
    {
        ["Authorization"] = "Bearer ${MCP_TEST_API_KEY}",
    },
    credentials: ["MCP_TEST_API_KEY"]);

// ── Agent ─────────────────────────────────────────────────────────────

var agent = new Agent("http_tools_demo")
{
    Model        = Settings.LlmModel,
    Tools        = [.. localTools, reverseApi, mcpTestTools],
    Instructions =
        "You can reverse strings and format reports. " +
        "When asked to reverse a string, use reverse_string first, then format_report with the result.",
};

// ── Run ───────────────────────────────────────────────────────────────

Console.WriteLine("=== HTTP and MCP Tools Demo ===");
await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    agent,
    "Reverse the string 'hello world' and add 33 and 21, append the result to that string, then write a report with the result.");
result.PrintResult();

// ── Tool class ────────────────────────────────────────────────────────

internal sealed class ReportFormatter
{
    [Tool("Format a title and body into a structured report.")]
    public Dictionary<string, object> FormatReport(string title, string body) =>
        new()
        {
            ["report"] = $"=== {title} ===\n{body}\n{new string('=', title.Length + 8)}",
        };
}
