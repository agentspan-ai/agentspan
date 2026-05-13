// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 12 — HTTP Tools: dedicated suite for HttpTools.Create() properties and plan integration.
//
// Corresponds to Python e2e: (HTTP tool aspect of test_suite3_cli_tools.py + Suite9 HTTP tests)
//
// Design notes:
//   - Suite9 mixes MCP and HTTP together. This suite focuses solely on HTTP tools.
//   - HttpTools.Create() returns a ToolDef with internal ToolType="http". The server
//     compiles this as a server-side Conductor HTTP task — no worker process is needed.
//   - ToolType and Config are internal, so [Fact] tests verify only public ToolDef
//     properties: Name, Credentials, External.
//   - [SkippableFact] tests call PlanAsync() and verify toolType="http" in the compiled plan.
//
// Two validation layers:
//   [Fact]          — pure SDK tests, no server. Inspect ToolDef public properties.
//   [SkippableFact] — server tests. Verify the compiled plan's tool types.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite12_HttpTools
{
    private readonly E2eFixture _fixture;

    public Suite12_HttpTools(E2eFixture fixture) => _fixture = fixture;

    // ── 12.1  HttpTools.Create() ToolDef has correct Name, Description, Credentials ──
    //
    // Counterfactual: if HttpTools.Create() did not carry Name and Credentials correctly,
    // the compiled plan would have an anonymous HTTP tool with no credential injection.

    [Fact]
    public void HttpTool_ToolDefHasNameDescriptionAndCredentials()
    {
        var tool = HttpTools.Create(
            name:        "fetch_weather",
            description: "Fetch current weather data from a REST API",
            url:         "https://api.weather.example.com/current",
            method:      "GET",
            credentials: ["WEATHER_API_KEY"]);

        Assert.Equal("fetch_weather",                          tool.Name);
        Assert.Equal("Fetch current weather data from a REST API", tool.Description);
        Assert.Contains("WEATHER_API_KEY", tool.Credentials);
        Assert.False(tool.External,
            "HttpTools.Create() must not set External=true — it is a server-side task.");

        // Counterfactual: without credentials the array must be empty
        var toolNoCreds = HttpTools.Create(
            name:        "plain_get",
            description: "No auth required",
            url:         "https://api.example.com/data");
        Assert.Empty(toolNoCreds.Credentials);
    }

    // ── 12.2  HttpTools with different HTTP methods — all create valid ToolDefs ──
    //
    // Counterfactual: if certain HTTP methods were rejected at construction time,
    // PUT/PATCH/DELETE endpoints could not be used without workarounds.

    [Fact]
    public void HttpTool_DifferentHttpMethods_AllCreateValidToolDefs()
    {
        var methods = new[] { "GET", "POST", "PUT", "PATCH", "DELETE" };

        foreach (var method in methods)
        {
            var tool = HttpTools.Create(
                name:        $"s12_{method.ToLowerInvariant()}_tool",
                description: $"HTTP {method} tool",
                url:         $"https://api.example.com/resource",
                method:      method);

            Assert.NotNull(tool);
            Assert.Contains($"s12_{method.ToLowerInvariant()}_tool", tool.Name);

            // Counterfactual: empty Name would fail when constructing the agent
            Assert.NotEmpty(tool.Name);
        }

        // Counterfactual: default method (GET) still creates a valid ToolDef
        var defaultMethod = HttpTools.Create(
            name:        "s12_default_method",
            description: "Uses default method",
            url:         "https://api.example.com/ping");
        Assert.NotNull(defaultMethod);
        Assert.Equal("s12_default_method", defaultMethod.Name);
    }

    // ── 12.3  HttpTools credential interpolation pattern — ${SECRET} in headers ──
    //
    // Verifies that ${SECRET}-style placeholders in headers are supported and
    // that the credential name is reflected in the local ToolDef.Credentials array.
    //
    // Counterfactual: if credential interpolation were not thread-safe or the name
    // was not propagated to Credentials, the server could not inject the secret
    // at runtime and the HTTP call would fail with a 401.

    [Fact]
    public void HttpTool_CredentialInterpolationPattern_ReflectedOnToolDef()
    {
        var tool = HttpTools.Create(
            name:        "s12_secure_post",
            description: "Post data with Authorization header",
            url:         "https://api.example.com/data",
            method:      "POST",
            headers:     new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${API_SECRET}",
                ["X-Client-Id"]   = "${CLIENT_ID}",
            },
            credentials: ["API_SECRET", "CLIENT_ID"]);

        Assert.Contains("API_SECRET",  tool.Credentials);
        Assert.Contains("CLIENT_ID",   tool.Credentials);
        Assert.Equal(2, tool.Credentials.Length);

        // Counterfactual: a tool with only one credential must not contain the other
        var singleCred = HttpTools.Create(
            name:        "s12_single_cred",
            description: "Single credential",
            url:         "https://api.example.com/other",
            credentials: ["API_SECRET"]);
        Assert.Contains("API_SECRET",        singleCred.Credentials);
        Assert.DoesNotContain("CLIENT_ID",   singleCred.Credentials);
    }

    // ── 12.4  HttpTool compiles with toolType="http" in plan ────────────────
    //
    // Counterfactual: if HttpTools were compiled as "worker", a worker process
    // would be required to execute the tool — defeating the purpose of a server-side HTTP task.

    [SkippableFact]
    public async Task HttpTool_CompilesWithHttpType()
    {
        _fixture.RequireServer();

        var tool = HttpTools.Create(
            name:        "s12_compile_check",
            description: "Compile check HTTP tool",
            url:         "https://api.example.com/ping",
            method:      "GET");

        var agent = new Agent("s12_http_compile_agent")
        {
            Model = Settings.LlmModel,
            Tools = [tool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("http", E2eHelpers.GetToolType(ad, "s12_compile_check"));

        // Counterfactual: agent without tools has no s12_compile_check
        var agentEmpty = new Agent("s12_http_empty") { Model = Settings.LlmModel };
        var planEmpty  = await runtime.PlanAsync(agentEmpty);
        var adEmpty    = E2eHelpers.GetAgentDef(planEmpty);
        Assert.DoesNotContain("s12_compile_check", E2eHelpers.ToolNames(adEmpty));
    }

    // ── 12.5  HttpTool with credentials: toolType="http" in plan ─────────────
    //
    // The server strips credential values from plan responses (security).
    // We verify only that the tool compiles as "http" (credential content is
    // verified on the local ToolDef in test 12.3).
    //
    // Counterfactual: if the credentials config format were wrong, the server
    // might reject the plan compilation entirely.

    [SkippableFact]
    public async Task HttpToolWithCredentials_CompilesWithHttpType()
    {
        _fixture.RequireServer();

        var tool = HttpTools.Create(
            name:        "s12_cred_http",
            description: "HTTP tool with credential",
            url:         "https://api.example.com/protected",
            method:      "POST",
            headers:     new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${HTTP_TEST_KEY}",
            },
            credentials: ["HTTP_TEST_KEY"]);

        // Verify credential on local object before compiling
        Assert.Contains("HTTP_TEST_KEY", tool.Credentials);

        var agent = new Agent("s12_http_cred_agent")
        {
            Model = Settings.LlmModel,
            Tools = [tool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // Server-side tool type must still be "http" even with credentials
        Assert.Equal("http", E2eHelpers.GetToolType(ad, "s12_cred_http"));

        // Counterfactual: a worker tool would appear as "worker", not "http"
        var workerTool = ToolDefFactory.Create(
            name:        "s12_worker_compare",
            description: "A local worker tool",
            handler:     (_, _) => Task.FromResult<object?>("ok"));
        var agentWorker = new Agent("s12_worker_agent") { Model = Settings.LlmModel, Tools = [workerTool] };
        var planWorker  = await runtime.PlanAsync(agentWorker);
        var adWorker    = E2eHelpers.GetAgentDef(planWorker);
        Assert.Equal("worker", E2eHelpers.GetToolType(adWorker, "s12_worker_compare"));
    }

    // ── 12.6  Agent with only HTTP tools has no worker tools in plan ─────────
    //
    // HTTP tools execute server-side; the plan should have no "worker" entries
    // when the agent only uses HTTP tools.
    //
    // Counterfactual: if HTTP tools were incorrectly classified as "worker", the
    // plan would require an external worker process for every HTTP call.

    [SkippableFact]
    public async Task AgentWithOnlyHttpTools_HasNoWorkerToolsInPlan()
    {
        _fixture.RequireServer();

        var http1 = HttpTools.Create(
            name:        "s12_multi_http_1",
            description: "First HTTP tool",
            url:         "https://api.example.com/first",
            method:      "GET");

        var http2 = HttpTools.Create(
            name:        "s12_multi_http_2",
            description: "Second HTTP tool",
            url:         "https://api.example.com/second",
            method:      "POST");

        var agent = new Agent("s12_http_only_agent")
        {
            Model = Settings.LlmModel,
            Tools = [http1, http2],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var toolNames = E2eHelpers.ToolNames(ad);
        Assert.Contains("s12_multi_http_1", toolNames);
        Assert.Contains("s12_multi_http_2", toolNames);

        // Neither tool should be a worker
        Assert.Equal("http", E2eHelpers.GetToolType(ad, "s12_multi_http_1"));
        Assert.Equal("http", E2eHelpers.GetToolType(ad, "s12_multi_http_2"));

        // No tool in the plan should have toolType="worker"
        var workerTools = toolNames
            .Where(name => E2eHelpers.GetToolType(ad, name) == "worker")
            .ToList();

        Assert.Empty(workerTools);

        // Counterfactual: adding a local tool would introduce a "worker" entry
        var localTool = ToolDefFactory.Create(
            name:        "s12_extra_worker",
            description: "A local worker",
            handler:     (_, _) => Task.FromResult<object?>("ok"));
        var mixed = new Agent("s12_mixed_check") { Model = Settings.LlmModel, Tools = [http1, localTool] };
        var planMixed = await runtime.PlanAsync(mixed);
        var adMixed   = E2eHelpers.GetAgentDef(planMixed);
        Assert.Equal("worker", E2eHelpers.GetToolType(adMixed, "s12_extra_worker"));
    }
}
