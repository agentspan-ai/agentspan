// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// HTTP Tools — server-side HTTP tools (no worker process needed).
//
// Demonstrates ToolDef with toolType="http" — the server calls the
// HTTP endpoint directly without dispatching to a local worker.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.Examples;

// ── Local worker tool ────────────────────────────────────────────────

var localTools = ToolRegistry.FromInstance(new ReportFormatter());

// ── HTTP tool (server-side, no local worker) ─────────────────────────
// The server calls the URL directly. ${HTTP_TEST_API_KEY} is resolved
// from the credential store at execution time.

var httpTool = new ToolDef
{
    Name        = "get_public_ip",
    Description = "Get the current public IP address",
    InputSchema = new JsonObject
    {
        ["type"]       = "object",
        ["properties"] = new JsonObject(),
        ["required"]   = new JsonArray(),
    },
    // Mark as external so AgentRuntime doesn't try to register a worker for it
    External = true,
};

// ── Agent ─────────────────────────────────────────────────────────────

var agent = new Agent("http_tools_demo")
{
    Model        = Settings.LlmModel,
    Instructions = "You can format reports. Use format_report to structure any information you have.",
    Tools        = [.. localTools, httpTool],
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Write a formatted report about the Agentspan C# SDK features.");
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
