// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// API Tool — auto-discover endpoints from OpenAPI, Swagger, or Postman specs.
//
// Demonstrates ApiTools.Create(), which points to an API spec and automatically
// discovers all operations as agent tools. The server fetches the spec at
// workflow startup, parses it, and makes each operation available to the LLM.
// No manual tool definitions needed — just point and go.
//
// Four patterns shown:
//   1. OpenAPI 3.x spec URL (local MCP test server with 65 deterministic tools)
//   2. Filtered operations — whitelist specific endpoints via ToolNames
//   3. Mixing ApiTool with other tool types
//   4. Large API with credential auth (GitHub)
//
// MCP Test Server Setup (mcp-testkit) — required for examples 1-3:
//   pip install mcp-testkit
//   mcp-testkit --transport http
//
// Requirements:
//   - Conductor server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - mcp-testkit running on http://localhost:3001 (for examples 1-3)
//   - GITHUB_TOKEN credential set (for example 4)

using Agentspan;
using Agentspan.Examples;

const string McpTestServerSpec = "http://localhost:3001/api-docs";

// ── Example 1: Full OpenAPI discovery ─────────────────────────
//
// Point to a live OpenAPI spec. The server discovers all operations,
// and the LLM picks the right one based on the user's request.

var mathApi = ApiTools.Create(
    url: McpTestServerSpec,
    name: "mcp_test_tools",
    headers: new() { ["Authorization"] = "Bearer ${HTTP_TEST_API_KEY}" },
    credentials: ["HTTP_TEST_API_KEY"],
    maxTools: 10);

var mathAgent = new Agent("math_assistant_71")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a math assistant. Use the API tools to compute results.",
    Tools        = [mathApi],
};

// ── Example 2: Filtered operations (ToolNames whitelist) ───────
//
// Whitelist specific operations by operationId. Only these are
// exposed to the LLM — everything else is ignored.

var stringApi = ApiTools.Create(
    url: McpTestServerSpec,
    headers: new() { ["Authorization"] = "Bearer ${HTTP_TEST_API_KEY}" },
    credentials: ["HTTP_TEST_API_KEY"],
    toolNames: ["string_reverse", "string_uppercase", "string_length"]);

var stringAgent = new Agent("string_assistant_71")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a string manipulation assistant.",
    Tools        = [stringApi],
};

// ── Example 3: Mix ApiTool with local tools ────────────────────
//
// ApiTools.Create works alongside McpTools, HttpTools, and [Tool]-decorated
// methods. The LLM sees all tools uniformly.

var collectionApi = ApiTools.Create(
    url: McpTestServerSpec,
    headers: new() { ["Authorization"] = "Bearer ${HTTP_TEST_API_KEY}" },
    credentials: ["HTTP_TEST_API_KEY"],
    toolNames: ["collection_sort", "collection_unique", "collection_flatten"],
    maxTools: 10);

var multiToolAgent = new Agent("multi_tool_assistant_71")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a versatile assistant. Use API tools for collection operations, " +
        "and the calculator for math. Pick the best tool for each request.",
    Tools        = [collectionApi, .. ToolRegistry.FromInstance(new Calculator())],
};

// ── Example 4: GitHub API with credential auth ─────────────────
//
// For large APIs (300+ operations), maxTools controls filtering.
// A lightweight LLM automatically selects the most relevant operations.
//
// Before running: set GITHUB_TOKEN credential in Agentspan server.

var github = ApiTools.Create(
    url: "https://api.github.com",
    headers: new()
    {
        ["Authorization"] = "token ${GITHUB_TOKEN}",
        ["Accept"]        = "application/vnd.github+json",
    },
    credentials: ["GITHUB_TOKEN"],
    toolNames: ["repos_list_for_user", "repos_create_for_authenticated_user",
                "issues_list_for_repo", "issues_create"],
    maxTools: 20);

var githubAgent = new Agent("github_assistant_71")
{
    Model        = Settings.LlmModel,
    Instructions = "You help users manage their GitHub repositories and issues.",
    Tools        = [github],
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

// Example 1: Math via OpenAPI-discovered tools
Console.WriteLine("=== Math API ===");
var result1 = await runtime.RunAsync(mathAgent, "What is 15 + 27? Also compute 8 factorial.");
result1.PrintResult();

// Example 2: Filtered string tools
Console.WriteLine("\n=== String API (filtered) ===");
var result2 = await runtime.RunAsync(stringAgent, "Reverse the string 'hello world' and tell me its length.");
result2.PrintResult();

// Example 3: Mixed tools
Console.WriteLine("\n=== Mixed Tools ===");
var result3 = await runtime.RunAsync(multiToolAgent, "Sort [3,1,4,1,5,9] and also compute sqrt(144).");
result3.PrintResult();

// ── Tool class ─────────────────────────────────────────────────

internal sealed class Calculator
{
    [Tool("Evaluate a simple math expression like '2 + 2' or 'sqrt(9)'.")]
    public Dictionary<string, object> Calculate(string expression)
    {
        try
        {
            // Simple eval for basic math (demo only — not for production use)
            var result = EvalMath(expression);
            return new() { ["expression"] = expression, ["result"] = result };
        }
        catch (Exception ex)
        {
            return new() { ["expression"] = expression, ["error"] = ex.Message };
        }
    }

    private static double EvalMath(string expr)
    {
        // Support basic operations: +, -, *, /, sqrt(), pow()
        expr = expr.Replace("sqrt(", "Math.Sqrt(").Replace("pow(", "Math.Pow(");
        var dt = new System.Data.DataTable();
        return Convert.ToDouble(dt.Compute(expr, ""));
    }
}
