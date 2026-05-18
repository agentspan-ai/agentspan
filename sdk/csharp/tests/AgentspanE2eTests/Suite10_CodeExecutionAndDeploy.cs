// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 10 — Code Execution Variants and Deploy Patterns.
//
// Corresponds to examples:
//   39a_DockerCodeExecution     — custom subprocess tool wrapping docker run
//   39c_ServerlessCodeExecution — custom HttpClient tool + local mock server
//   63d_ServeFromAssembly       — reflection-based agent discovery
//   63e_RunMonitoring           — RunByNameAsync to trigger a deployed agent
//
// Validation strategy:
//   [Fact]          — local SDK/tool behavior, no server, no LLM.
//   [SkippableFact] — server plan/execution tests.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Net;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite10_CodeExecutionAndDeploy
{
    private readonly E2eFixture _fixture;

    public Suite10_CodeExecutionAndDeploy(E2eFixture fixture) => _fixture = fixture;

    // ── 10.1  DockerExecutor registers as a tool via ToolRegistry ────────────

    [Fact]
    public void DockerExecutor_RegistersAsTool()
    {
        var tools = ToolRegistry.FromInstance(new S10DockerExecutor());

        Assert.True(tools.Count > 0, "S10DockerExecutor must expose at least one tool.");
        Assert.True(tools.Any(t => t.Name == "execute_in_docker"),
            "Tool name must be 'execute_in_docker'.");

        // Counterfactual: empty host has no tools
        var empty = ToolRegistry.FromInstance(new object());
        Assert.Empty(empty);
    }

    // ── 10.2  Docker executor tool compiles in a plan ────────────────────────

    [SkippableFact]
    public async Task DockerExecutor_CompilesInPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s10_docker_plan")
        {
            Model = Settings.LlmModel,
            Tools = ToolRegistry.FromInstance(new S10DockerExecutor()),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "execute_in_docker"));

        // Counterfactual: agent without docker tool has no execute_in_docker
        var agentEmpty = new Agent("s10_no_docker") { Model = Settings.LlmModel };
        var planEmpty  = await runtime.PlanAsync(agentEmpty);
        var adEmpty    = E2eHelpers.GetAgentDef(planEmpty);
        Assert.DoesNotContain("execute_in_docker", E2eHelpers.ToolNames(adEmpty));
    }

    // ── 10.3  ServerlessExecutor tool registers correctly ────────────────────

    [Fact]
    public void ServerlessExecutor_RegistersAsTool()
    {
        var tools = ToolRegistry.FromInstance(new S10ServerlessExecutor("http://127.0.0.1:9999/execute"));

        Assert.True(tools.Count > 0, "S10ServerlessExecutor must expose at least one tool.");
        Assert.True(tools.Any(t => t.Name == "execute_code"),
            "Tool name must be 'execute_code'.");
    }

    // ── 10.4  ServerlessExecutor actually sends code to mock HTTP server ─────

    [Fact]
    public async Task ServerlessExecutor_PostsCodeToEndpoint()
    {
        const int port = 19753;

        // Spin up a tiny mock execution server
        var listener = new HttpListener();
        listener.Prefixes.Add($"http://127.0.0.1:{port}/");
        listener.Start();

        int callCount = 0;
        string? receivedCode = null;

        var serverTask = Task.Run(async () =>
        {
            var ctx = await listener.GetContextAsync();
            using var reader = new System.IO.StreamReader(ctx.Request.InputStream);
            var body = await reader.ReadToEndAsync();
            var req  = JsonNode.Parse(body);
            receivedCode = req?["code"]?.GetValue<string>();
            Interlocked.Increment(ref callCount);

            var resp  = """{"output":"hello","error":"","exit_code":0}""";
            var bytes = Encoding.UTF8.GetBytes(resp);
            ctx.Response.ContentType = "application/json";
            ctx.Response.ContentLength64 = bytes.Length;
            await ctx.Response.OutputStream.WriteAsync(bytes);
            ctx.Response.Close();
            listener.Stop();
        });

        // Call the executor tool directly (not via LLM)
        var executor = new S10ServerlessExecutor($"http://127.0.0.1:{port}/execute");
        var result   = await executor.ExecuteCode("print('hello')");

        await serverTask;

        Assert.Equal(1, callCount);
        Assert.Equal("print('hello')", receivedCode);
        Assert.Equal("hello", result);

        // Counterfactual: a different code string is sent as-is
        Assert.NotEqual("print('world')", receivedCode);
    }

    // ── 10.5  ServerlessExecutor compiles in a plan ──────────────────────────

    [SkippableFact]
    public async Task ServerlessExecutor_CompilesInPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s10_serverless_plan")
        {
            Model = Settings.LlmModel,
            Tools = ToolRegistry.FromInstance(new S10ServerlessExecutor("http://127.0.0.1:9753/execute")),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "execute_code"));
    }

    // ── 10.6  DiscoverAgents finds all static Agent properties in assembly ───

    [Fact]
    public void DiscoverAgents_FindsAllStaticAgents()
    {
        // Scan only our test-local library (in this assembly)
        var agents = DiscoverAgents(typeof(S10AgentLibrary).Assembly,
            type => type == typeof(S10AgentLibrary));

        Assert.True(agents.Count >= 2,
            $"Expected >= 2 agents in S10AgentLibrary but got {agents.Count}.");
        Assert.True(agents.Any(a => a.Name == "s10_monitoring"),
            "s10_monitoring must be discovered.");
        Assert.True(agents.Any(a => a.Name == "s10_reporter"),
            "s10_reporter must be discovered.");

        // Counterfactual: scanning a type with no agents yields empty list
        var emptyResult = DiscoverAgents(typeof(S10AgentLibrary).Assembly,
            type => type == typeof(Suite10_CodeExecutionAndDeploy));
        Assert.Empty(emptyResult);
    }

    // ── 10.7  Discovered agents compile on the server ────────────────────────

    [SkippableFact]
    public async Task DiscoveredAgents_CompileOnServer()
    {
        _fixture.RequireServer();

        var agents = DiscoverAgents(typeof(S10AgentLibrary).Assembly,
            type => type == typeof(S10AgentLibrary));

        await using var runtime = new AgentRuntime();
        foreach (var agent in agents)
        {
            var plan = await runtime.PlanAsync(agent);
            Assert.True(plan?["workflowDef"] is not null,
                $"Agent '{agent.Name}' must compile to a plan with workflowDef.");
        }
    }

    // ── 10.8  RunByNameAsync targets a previously deployed agent ─────────────

    [SkippableFact]
    public async Task RunByNameAsync_ExecutesDeployedAgent()
    {
        _fixture.RequireServer();

        // Deploy monitoring_63d first (it uses no local worker tools)
        var agent = new Agent("s10_run_by_name_agent")
        {
            Model        = Settings.LlmModel,
            Instructions = "Reply with exactly: HEALTHY",
        };

        await using var runtime = new AgentRuntime();

        // First run registers the workflow
        var r1 = await runtime.RunAsync(agent, "Status?");
        Assert.True(r1.IsSuccess, $"First run failed: {r1.Error}");

        // Second run by name — no Agent object required
        var r2 = await runtime.RunByNameAsync("s10_run_by_name_agent", "Status?");
        Assert.True(r2.IsSuccess, $"RunByNameAsync failed: {r2.Error}");

        // Counterfactual: RunByNameAsync for a non-existent name must throw (404)
        await Assert.ThrowsAnyAsync<Exception>(
            () => runtime.RunByNameAsync("s10_does_not_exist_xyz", "?"));
    }

    // ── 10.9  Runtime: local Python execution produces expected output ───
    //
    // Ports Python suite10 test_local_python_execution. Asserts the
    // execute_code task ran and the stdout contains '3066'.

    [SkippableFact]
    public async Task LocalPython_RuntimeProducesExpectedOutput()
    {
        _fixture.RequireServer();

        // Mirrors Java Suite10CodeExecution.test_local_python_execution which
        // passes consistently in CI. Same prompt, same recipe — the simple
        // print(42*73) is sufficient when paired with allowedLanguages=[python]
        // (broader allowedLanguages seemed to make gpt-4o-mini skip the tool).
        var agent = new Agent("s10_local_py_rt")
        {
            Model               = Settings.LlmModel,
            LocalCodeExecution  = true,
            AllowedLanguages    = ["python"],
            MaxTurns            = 5,
            Instructions =
                "You can execute code using the execute_code tool. " +
                "When asked to run Python code, you MUST call execute_code with " +
                "language='python' and the exact code provided. Do not compute mentally — " +
                "always use the execute_code tool.",
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        var result = await runtime.RunAsync(
            agent,
            "Run this exact Python code using execute_code: print(42 * 73)",
            ct: cts.Token);

        Assert.True(result.IsSuccess,
            $"[LocalPy] Expected COMPLETED, got '{result.Status}'. Error: {result.Error}");

        var execTasks = await FindExecuteCodeTasksAsync(result.ExecutionId);
        Assert.True(execTasks.Count >= 1, "[LocalPy] No execute_code tasks in workflow.");
        Assert.True(execTasks.Any(t => (t["outputData"]?.ToString() ?? "").Contains("3066")),
            "[LocalPy] '3066' not found in any execute_code task outputData.");
    }

    // ── 10.10  Runtime: short timeout kills long-running code ────────────
    //
    // Ports Python suite10 test_local_timeout. Configures the executor with
    // a 3-second timeout against a sleep(30) script and asserts the stdout
    // never contains "done".

    [SkippableFact]
    public async Task LocalTimeout_KillsLongRunningCode()
    {
        _fixture.RequireServer();

        var agent = new Agent("s10_local_timeout_rt")
        {
            Model              = Settings.LlmModel,
            MaxTurns           = 2,
            LocalCodeExecution = true,
            CodeExecution      = new CodeExecutionConfig(
                AllowedLanguages: ["python"],
                Timeout: 3),
            Instructions =
                "You execute Python code. When asked to run code, execute it via execute_code " +
                "exactly as provided. Do not modify the code.",
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(75));
        var result = await runtime.RunAsync(
            agent,
            "Run this exact Python code using execute_code: import time; time.sleep(30); print(\"done\")",
            ct: cts.Token);

        // Agent may end with various terminal statuses; the assertion below is the real one.
        Assert.NotEmpty(result.ExecutionId);

        var execTasks = await FindExecuteCodeTasksAsync(result.ExecutionId);
        foreach (var task in execTasks)
        {
            var output = task["outputData"]?.ToString() ?? "";
            Assert.DoesNotContain("\"done\"", output);
        }
    }

    private async Task<List<JsonNode>> FindExecuteCodeTasksAsync(string executionId)
    {
        var wf = await _fixture.FetchWorkflowAsync(executionId);
        var tasks = wf?["tasks"]?.AsArray();
        var matched = new List<JsonNode>();
        if (tasks is null) return matched;
        foreach (var t in tasks)
        {
            if (t is null) continue;
            var ref_ = t["referenceTaskName"]?.GetValue<string>() ?? "";
            var def  = t["taskDefName"]?.GetValue<string>() ?? "";
            if (ref_.Contains("execute_code") || def.Contains("execute_code"))
                matched.Add(t);
        }
        return matched;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static List<Agent> DiscoverAgents(Assembly assembly, Func<Type, bool>? filter = null)
    {
        var agents = new List<Agent>();
        foreach (var type in assembly.GetTypes())
        {
            if (filter is not null && !filter(type)) continue;

            foreach (var prop in type.GetProperties(BindingFlags.Public | BindingFlags.Static))
                if (prop.PropertyType == typeof(Agent) && prop.GetValue(null) is Agent a)
                    agents.Add(a);

            foreach (var field in type.GetFields(BindingFlags.Public | BindingFlags.Static))
                if (field.FieldType == typeof(Agent) && field.GetValue(null) is Agent a)
                    agents.Add(a);
        }
        return agents;
    }
}

// ── Tool hosts ────────────────────────────────────────────────────────────────

/// <summary>Stub Docker executor (no real docker call needed for compilation tests).</summary>
internal sealed class S10DockerExecutor
{
    [Tool("Execute Python code in an isolated Docker container. Returns stdout/stderr.")]
    public Task<string> ExecuteInDocker(string code)
        => Task.FromResult($"[stub] would run in docker: {code[..Math.Min(40, code.Length)]}");
}

/// <summary>Serverless executor that POSTs code to an HTTP endpoint.</summary>
internal sealed class S10ServerlessExecutor(string endpoint)
{
    private static readonly HttpClient _http = new();

    [Tool("Execute Python code on a remote execution service. Returns stdout/stderr.")]
    public async Task<string> ExecuteCode(string code, int timeoutSeconds = 15)
    {
        using var content = new StringContent(
            System.Text.Json.JsonSerializer.Serialize(new { code, language = "python", timeout = timeoutSeconds }),
            Encoding.UTF8, "application/json");

        using var resp = await _http.PostAsync(endpoint, content);
        var body   = await resp.Content.ReadAsStringAsync();
        var result = JsonNode.Parse(body);
        var output = result?["output"]?.GetValue<string>() ?? "";
        var error  = result?["error"]?.GetValue<string>()  ?? "";
        var exit   = result?["exit_code"]?.GetValue<int>() ?? -1;
        return exit == 0 ? output.Trim() : $"Error (exit {exit}): {error.Trim()}";
    }
}

/// <summary>Static agent library for discovery tests.</summary>
internal static class S10AgentLibrary
{
    public static Agent MonitoringAgent { get; } = new Agent("s10_monitoring")
    {
        Model        = Settings.LlmModel,
        Instructions = "You monitor system health.",
    };

    public static Agent ReporterAgent { get; } = new Agent("s10_reporter")
    {
        Model        = Settings.LlmModel,
        Instructions = "You generate status reports.",
    };
}
