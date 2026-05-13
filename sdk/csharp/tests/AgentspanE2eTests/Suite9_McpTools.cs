// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 9 — MCP and HTTP Tools: server-side tool types and credential declaration.
//
// Corresponds to examples:
//   04_HttpAndMcpTools    — mixing local worker, HTTP tool, and MCP tool
//   04_McpWeather         — MCP-only agent
//   16f_CredentialsMcpTool — MCP tool with credential-bearing headers
//
// Design notes:
//   - McpTools.Create() and HttpTools.Create() return ToolDef objects with
//     internal ToolType="mcp"/"http". The server compiles these as server-side
//     tasks; no worker process is needed for them.
//   - ToolType and Config are internal, so [Fact] tests verify only the public
//     ToolDef properties: Name, Credentials, External.
//   - [SkippableFact] tests call PlanAsync() and verify toolType in the compiled
//     plan response ("mcp" / "http" / "worker").
//
// Two validation layers:
//   [Fact]          — pure SDK tests, no server. Inspect ToolDef public properties.
//   [SkippableFact] — server tests. Verify the compiled plan's tool types.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite9_McpTools
{
    private readonly E2eFixture _fixture;

    public Suite9_McpTools(E2eFixture fixture) => _fixture = fixture;

    // ── 9.1  McpTools.Create() returns a ToolDef with correct public properties ──

    [Fact]
    public void McpTool_ToolDefHasNameAndCredentials()
    {
        var mcp = McpTools.Create(
            serverUrl:   "http://localhost:3001/mcp",
            name:        "weather_mcp",
            description: "Weather tools via MCP",
            headers:     new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${MCP_TEST_API_KEY}",
            },
            credentials: ["MCP_TEST_API_KEY"]);

        Assert.Equal("weather_mcp", mcp.Name);
        Assert.Contains("MCP_TEST_API_KEY", mcp.Credentials);
        Assert.False(mcp.External,
            "McpTools.Create() must not set External=true — it is a server-side task, not an external worker.");

        // Counterfactual: default name when omitted is "mcp_tools"
        var mcpDefault = McpTools.Create(serverUrl: "http://localhost:3001/mcp");
        Assert.Equal("mcp_tools", mcpDefault.Name);
        Assert.Empty(mcpDefault.Credentials);
    }

    // ── 9.2  HttpTools.Create() returns a ToolDef with correct public properties ──

    [Fact]
    public void HttpTool_ToolDefHasNameAndCredentials()
    {
        var http = HttpTools.Create(
            name:        "reverse_string",
            description: "Reverse a string using the HTTP API",
            url:         "http://localhost:3001/api/string/reverse",
            method:      "POST",
            headers:     new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${HTTP_TEST_API_KEY}",
            },
            credentials: ["HTTP_TEST_API_KEY"]);

        Assert.Equal("reverse_string", http.Name);
        Assert.Contains("HTTP_TEST_API_KEY", http.Credentials);
        Assert.False(http.External,
            "HttpTools.Create() must not set External=true — it is a server-side task, not an external worker.");

        // Counterfactual: HttpTools without credentials has empty credentials
        var httpNoCred = HttpTools.Create(
            name:        "plain_http",
            description: "No auth",
            url:         "http://example.com/api");
        Assert.Empty(httpNoCred.Credentials);
    }

    // ── 9.3  Multiple credential keys on McpTools.Create() ──────────────────

    [Fact]
    public void McpTool_MultipleCredentialsAllPresent()
    {
        var mcp = McpTools.Create(
            serverUrl:   "http://localhost:3001/mcp",
            credentials: ["MCP_API_KEY", "OTHER_KEY"]);

        Assert.Contains("MCP_API_KEY",  mcp.Credentials);
        Assert.Contains("OTHER_KEY",    mcp.Credentials);
        Assert.Equal(2, mcp.Credentials.Length);

        // Counterfactual: single-credential tool must not include OTHER_KEY
        var single = McpTools.Create(
            serverUrl:   "http://localhost:3001/mcp",
            credentials: ["MCP_API_KEY"]);
        Assert.DoesNotContain("OTHER_KEY", single.Credentials);
    }

    // ── 9.4  MCP tool appears in compiled plan with toolType "mcp" ──────────

    [SkippableFact]
    public async Task McpTool_AppearsInPlanWithMcpType()
    {
        _fixture.RequireServer();

        var mcp = McpTools.Create(
            serverUrl:   "http://localhost:3001/mcp",
            name:        "s9_weather_mcp",
            description: "Weather tools via MCP",
            credentials: ["MCP_TEST_API_KEY"]);

        var agent = new Agent("s9_mcp_plan_check")
        {
            Model = Settings.LlmModel,
            Tools = [mcp],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("mcp", E2eHelpers.GetToolType(ad, "s9_weather_mcp"));

        // Counterfactual: an agent without tools has no s9_weather_mcp
        var agentEmpty = new Agent("s9_no_tools_check") { Model = Settings.LlmModel };
        var planEmpty  = await runtime.PlanAsync(agentEmpty);
        var adEmpty    = E2eHelpers.GetAgentDef(planEmpty);
        Assert.DoesNotContain("s9_weather_mcp", E2eHelpers.ToolNames(adEmpty));
    }

    // ── 9.5  HTTP tool appears in compiled plan with toolType "http" ─────────

    [SkippableFact]
    public async Task HttpTool_AppearsInPlanWithHttpType()
    {
        _fixture.RequireServer();

        var http = HttpTools.Create(
            name:        "s9_reverse_string",
            description: "Reverse a string using the HTTP API",
            url:         "http://localhost:3001/api/string/reverse",
            method:      "POST",
            credentials: ["HTTP_TEST_API_KEY"]);

        var agent = new Agent("s9_http_plan_check")
        {
            Model = Settings.LlmModel,
            Tools = [http],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("http", E2eHelpers.GetToolType(ad, "s9_reverse_string"));

        // Counterfactual: agent with only MCP tool must not have s9_reverse_string
        var mcpOnly = McpTools.Create(
            serverUrl: "http://localhost:3001/mcp",
            name:      "s9_mcp_only");
        var agentMcpOnly = new Agent("s9_mcp_only_agent")
        {
            Model = Settings.LlmModel,
            Tools = [mcpOnly],
        };
        var planMcpOnly = await runtime.PlanAsync(agentMcpOnly);
        var adMcpOnly   = E2eHelpers.GetAgentDef(planMcpOnly);
        Assert.DoesNotContain("s9_reverse_string", E2eHelpers.ToolNames(adMcpOnly));
    }

    // ── 9.6  Mixed agent: MCP, HTTP, and worker tools each have correct type ─

    [SkippableFact]
    public async Task MixedAgent_AllThreeToolTypes()
    {
        _fixture.RequireServer();

        var mcp  = McpTools.Create(
            serverUrl: "http://localhost:3001/mcp",
            name:      "s9_mixed_mcp");
        var http = HttpTools.Create(
            name:        "s9_mixed_http",
            description: "HTTP tool",
            url:         "http://localhost:3001/api/string/reverse",
            method:      "POST");
        var worker = ToolDefFactory.Create(
            name:        "s9_mixed_worker",
            description: "Local worker tool",
            handler:     (_, _) => Task.FromResult<object?>("ok"));

        var agent = new Agent("s9_mixed_types")
        {
            Model = Settings.LlmModel,
            Tools = [mcp, http, worker],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("mcp",    E2eHelpers.GetToolType(ad, "s9_mixed_mcp"));
        Assert.Equal("http",   E2eHelpers.GetToolType(ad, "s9_mixed_http"));
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "s9_mixed_worker"));
    }

    // ── 9.7  MCP credential tool: credential declared on local ToolDef ────────
    //
    // Mirrors 16f_CredentialsMcpTool. The server strips credential names
    // from plan responses for security; we verify via the local ToolDef.

    [Fact]
    public void McpCredentialTool_CredentialDeclaredOnToolDef()
    {
        var mcp = McpTools.Create(
            serverUrl:   "http://localhost:3001/mcp",
            headers:     new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${MCP_API_KEY}",
            },
            credentials: ["MCP_API_KEY"]);

        Assert.Contains("MCP_API_KEY", mcp.Credentials);
        Assert.Single(mcp.Credentials);

        // Counterfactual: MCP tool without credentials has empty credentials
        var mcpNoCred = McpTools.Create(serverUrl: "http://localhost:3001/mcp");
        Assert.Empty(mcpNoCred.Credentials);
    }

    // ── 9.8  MCP credential tool compiles on server with toolType "mcp" ─────────

    [SkippableFact]
    public async Task McpCredentialTool_CompilesWithMcpType()
    {
        _fixture.RequireServer();

        var mcp = McpTools.Create(
            serverUrl:   "http://localhost:3001/mcp",
            name:        "s9_cred_mcp",
            headers:     new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${MCP_API_KEY}",
            },
            credentials: ["MCP_API_KEY"]);

        var agent = new Agent("s9_cred_mcp_agent")
        {
            Model = Settings.LlmModel,
            Tools = [mcp],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("mcp", E2eHelpers.GetToolType(ad, "s9_cred_mcp"));
    }
}
