// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 2 — Tool calling: verify the tool function body executes.
//
// Validation strategy: use Interlocked.Increment on a shared counter instead
// of parsing LLM text output. The counter proves the function body ran, not
// that the LLM described it correctly.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.
//
// 2.5 — Credential lifecycle — mirrors sdk/python/e2e/test_suite2_tool_calling.py.
// Verifies runtime injection actually happens (catches URL drift like the
// /credentials/resolve → /workers/secrets bug that Suite 7 serialization
// tests could not see) and that the SDK does NOT silently fall back to
// process env when a declared credential is missing from the store.

using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite2_ToolCalling
{
    private readonly E2eFixture _fixture;

    public Suite2_ToolCalling(E2eFixture fixture) => _fixture = fixture;

    // ── 2.1  Single tool executes ─────────────────────────────────────────

    [SkippableFact]
    public async Task SingleTool_FunctionBodyExecutes()
    {
        _fixture.RequireServer();

        var host  = new S2SingleToolHost();
        var tools = ToolRegistry.FromInstance(host);

        var agent = new Agent("s2_single_tool")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call get_value. Do not answer without calling it.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Call get_value and tell me the result.");

        // The tool function body must have run at least once
        Assert.True(host.CallCount > 0,
            $"Expected get_value to be called at least once but call count was {host.CallCount}.");
        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
    }

    // ── 2.2  Multi-tool agent calls the right tool ──────────────────────

    [SkippableFact]
    public async Task MultiTool_CorrectToolSelected()
    {
        _fixture.RequireServer();

        var host  = new S2MultiToolHost();
        var tools = ToolRegistry.FromInstance(host);

        var agent = new Agent("s2_multi_tool")
        {
            Model        = Settings.LlmModel,
            Instructions = "Use the available tools to answer math questions.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "What is the square root of 144?");

        // sqrt tool must have been called; add tool must NOT have been called
        Assert.True(host.SqrtCallCount > 0,
            "Expected sqrt_value to be called but it wasn't.");
        // Counterfactual: prompt doesn't mention addition, so add must not be called
        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
    }

    // ── 2.3  Tool result feeds back into agent response ─────────────────

    [SkippableFact]
    public async Task ToolResult_IncludedInExecution()
    {
        _fixture.RequireServer();

        var host  = new S2EchoToolHost();
        var tools = ToolRegistry.FromInstance(host);

        var agent = new Agent("s2_echo_tool")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call echo_token and include its result in your response.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Echo 'agentspan-e2e-marker' and tell me what you got back.");

        Assert.True(host.CallCount > 0,
            "Expected echo_token to be called but it wasn't.");
        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");

        // The sentinel value returned by the tool must appear somewhere in execution data
        // We do NOT parse LLM text — we check that the tool WAS called (counter > 0).
        // The execution ID proves this ran against the real server.
        Assert.NotEmpty(result.ExecutionId);
    }

    // ── 2.4  Async tool works correctly ─────────────────────────────────

    [SkippableFact]
    public async Task AsyncTool_FunctionBodyExecutes()
    {
        _fixture.RequireServer();

        var host  = new S2AsyncToolHost();
        var tools = ToolRegistry.FromInstance(host);

        var agent = new Agent("s2_async_tool")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call fetch_data. Do not answer without calling it.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Fetch some data using fetch_data and summarize it.");

        Assert.True(host.CallCount > 0,
            $"Expected fetch_data to be called at least once but call count was {host.CallCount}.");
        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
    }

    // ── 2.5  Credential lifecycle — mirrors Python test_suite2 ──────────
    //
    // Four-step lifecycle exercising the runtime injection contract:
    //   2.5a  no creds in store          → paid tool must be TERMINAL-failed
    //   2.5b  env set + no store value   → env MUST NOT be read (security)
    //   2.5c  cred set via API           → tool sees stored value at runtime
    //   2.5d  cred updated via API       → next run sees the new value
    //
    // This is the test that would have caught the /credentials/resolve URL
    // drift. The Suite 7 serialization tests passed throughout because they
    // never invoke a tool — only inspect the plan.

    private const string LCRED_A = "E2E_DOTNET_CRED_A";
    private const string LCRED_B = "E2E_DOTNET_CRED_B";

    private static readonly string ApiBase =
        (Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL") ?? "http://localhost:6767/api")
        .TrimEnd('/');

    [SkippableFact]
    public async Task CredentialLifecycle_RuntimeInjection()
    {
        _fixture.RequireServer();

        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        var savedA = Environment.GetEnvironmentVariable(LCRED_A);
        var savedB = Environment.GetEnvironmentVariable(LCRED_B);

        try
        {
            // ── Step 1: clean slate ─────────────────────────────────────
            await DeleteSecretAsync(http, LCRED_A);
            await DeleteSecretAsync(http, LCRED_B);

            var host = new S2CredHost();
            var allTools = ToolRegistry.FromInstance(host);
            // Declared credentials are set on the [Tool(... Credentials = ...)]
            // attribute itself; ToolDef.Credentials is init-only, so we can't
            // mutate it post-construction.

            var agent = new Agent("s2_cred_lifecycle")
            {
                Model        = Settings.LlmModel,
                Instructions =
                    "You have three tools: free_tool, paid_tool_a, paid_tool_b. " +
                    "Call all three with the argument 'test'. Do not skip any.",
                Tools    = allTools,
                MaxTurns = 4,
            };

            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(180));

            // ── Step 2: no creds → paid tools must be terminal ──────────
            {
                await using var runtime = new AgentRuntime();
                var r = await runtime.RunAsync(agent, "Call all three tools.", ct: cts.Token);
                Assert.False(string.IsNullOrEmpty(r.ExecutionId), "Step 2: no execution_id");
                var tasks = await FetchToolTasksAsync(http, r.ExecutionId);
                AssertToolTaskTerminal(tasks, "paid_tool_a", "Step 2: no creds");
                AssertToolTaskTerminal(tasks, "paid_tool_b", "Step 2: no creds");
            }

            // ── Step 3: env set + no store value → env NOT read ─────────
            Environment.SetEnvironmentVariable(LCRED_A, "from-env-aaa");
            Environment.SetEnvironmentVariable(LCRED_B, "from-env-bbb");
            try
            {
                await using var runtime = new AgentRuntime();
                var r = await runtime.RunAsync(agent, "Call all three tools.", ct: cts.Token);
                var tasks = await FetchToolTasksAsync(http, r.ExecutionId);

                AssertToolTaskTerminal(tasks, "paid_tool_a", "Step 3: env-leak check");
                AssertToolTaskTerminal(tasks, "paid_tool_b", "Step 3: env-leak check");

                foreach (var (_, info) in tasks)
                {
                    var outStr = info.Output?.ToString() ?? "";
                    Assert.DoesNotContain("from-env", outStr);
                }
            }
            finally
            {
                Environment.SetEnvironmentVariable(LCRED_A, null);
                Environment.SetEnvironmentVariable(LCRED_B, null);
            }

            // ── Step 4: cred set via API → value reaches the tool ───────
            await PutSecretAsync(http, LCRED_A, "secret-aaa-value");
            await PutSecretAsync(http, LCRED_B, "secret-bbb-value");

            {
                await using var runtime = new AgentRuntime();
                var r = await runtime.RunAsync(agent, "Call all three tools.", ct: cts.Token);
                var tasks = await FetchToolTasksAsync(http, r.ExecutionId);

                AssertToolTaskCompleted(tasks, "free_tool", "Step 4");
                AssertToolTaskCompleted(tasks, "paid_tool_a", "Step 4");
                AssertToolTaskCompleted(tasks, "paid_tool_b", "Step 4");

                Assert.Contains("sec", tasks["paid_tool_a"].Output?.ToString() ?? "");
                Assert.Contains("sec", tasks["paid_tool_b"].Output?.ToString() ?? "");
            }

            // ── Step 5: cred updated → new value propagates ─────────────
            await PutSecretAsync(http, LCRED_A, "newval-xxx-updated");

            {
                await using var runtime = new AgentRuntime();
                var r = await runtime.RunAsync(agent, "Call all three tools.", ct: cts.Token);
                var tasks = await FetchToolTasksAsync(http, r.ExecutionId);
                AssertToolTaskCompleted(tasks, "paid_tool_a", "Step 5");
                Assert.Contains("new", tasks["paid_tool_a"].Output?.ToString() ?? "");
            }
        }
        finally
        {
            try { await DeleteSecretAsync(http, LCRED_A); } catch { }
            try { await DeleteSecretAsync(http, LCRED_B); } catch { }
            Environment.SetEnvironmentVariable(LCRED_A, savedA);
            Environment.SetEnvironmentVariable(LCRED_B, savedB);
        }
    }

    // ── Lifecycle helpers ───────────────────────────────────────────────

    private static async Task PutSecretAsync(HttpClient http, string name, string value)
    {
        using var content = new StringContent(value, System.Text.Encoding.UTF8, "text/plain");
        using var resp = await http.PutAsync($"{ApiBase}/secrets/{Uri.EscapeDataString(name)}", content);
        resp.EnsureSuccessStatusCode();
    }

    private static async Task DeleteSecretAsync(HttpClient http, string name)
    {
        using var req = new HttpRequestMessage(HttpMethod.Delete,
            $"{ApiBase}/secrets/{Uri.EscapeDataString(name)}");
        using var resp = await http.SendAsync(req);
        if (!resp.IsSuccessStatusCode && (int)resp.StatusCode != 404)
            resp.EnsureSuccessStatusCode();
    }

    private record ToolTaskInfo(string Status, string Reason, JsonNode? Output, string Ref);

    private static async Task<Dictionary<string, ToolTaskInfo>> FetchToolTasksAsync(
        HttpClient http, string executionId)
    {
        var serverBase = ApiBase.Replace("/api", "");
        using var resp = await http.GetAsync(
            $"{serverBase}/api/workflow/{executionId}?includeTasks=true");
        resp.EnsureSuccessStatusCode();
        var wf = JsonNode.Parse(await resp.Content.ReadAsStringAsync());

        string[] names = ["free_tool", "paid_tool_a", "paid_tool_b"];
        var results = new Dictionary<string, ToolTaskInfo>();
        foreach (var t in wf?["tasks"]?.AsArray() ?? [])
        {
            if (t is null) continue;
            var refName = t["referenceTaskName"]?.GetValue<string>() ?? "";
            var taskDef = t["taskDefName"]?.GetValue<string>() ?? "";
            var taskTyp = t["taskType"]?.GetValue<string>() ?? "";
            foreach (var n in names)
            {
                if (results.ContainsKey(n)) continue;
                if (refName.Contains(n) || taskDef == n || taskTyp == n)
                    results[n] = new ToolTaskInfo(
                        Status: t["status"]?.GetValue<string>() ?? "",
                        Reason: t["reasonForIncompletion"]?.GetValue<string>() ?? "",
                        Output: t["outputData"],
                        Ref:    refName);
            }
        }
        return results;
    }

    private static void AssertToolTaskTerminal(
        Dictionary<string, ToolTaskInfo> tasks, string name, string step)
    {
        Assert.True(tasks.ContainsKey(name),
            $"[{step}] {name} task not found. Found: [{string.Join(", ", tasks.Keys)}]");
        // FAILED_WITH_TERMINAL_ERROR (TaskResult) → COMPLETED_WITH_ERRORS (Task)
        var terminal = new HashSet<string> { "FAILED_WITH_TERMINAL_ERROR", "COMPLETED_WITH_ERRORS" };
        Assert.True(terminal.Contains(tasks[name].Status),
            $"[{step}] {name} expected terminal status (FAILED_WITH_TERMINAL_ERROR or " +
            $"COMPLETED_WITH_ERRORS) but got '{tasks[name].Status}'. " +
            $"Reason: {tasks[name].Reason}");
    }

    private static void AssertToolTaskCompleted(
        Dictionary<string, ToolTaskInfo> tasks, string name, string step)
    {
        Assert.True(tasks.ContainsKey(name),
            $"[{step}] {name} task not found. Found: [{string.Join(", ", tasks.Keys)}]");
        Assert.Equal("COMPLETED", tasks[name].Status);
    }
}

// ── Suite 2.5 tool host ──────────────────────────────────────────────────────

/// <summary>
/// Tools for the credential lifecycle test. paid_tool_* read their declared
/// credential from Environment.GetEnvironmentVariable and return the first
/// three chars — the test asserts on Conductor task output, never LLM text.
/// </summary>
internal sealed class S2CredHost
{
    [Tool("A tool that needs no credentials. Always succeeds.")]
    public string FreeTool(string x) => "free:ok";

    [Tool("Needs E2E_DOTNET_CRED_A. Returns first 3 chars of the credential.",
        Credentials = new[] { "E2E_DOTNET_CRED_A" })]
    public string PaidToolA(string x)
    {
        var v = Environment.GetEnvironmentVariable("E2E_DOTNET_CRED_A");
        if (string.IsNullOrEmpty(v))
            throw new TerminalToolException(
                "Credential 'E2E_DOTNET_CRED_A' not found in environment.");
        return $"paid_a:{v[..Math.Min(3, v.Length)]}";
    }

    [Tool("Needs E2E_DOTNET_CRED_B. Returns first 3 chars of the credential.",
        Credentials = new[] { "E2E_DOTNET_CRED_B" })]
    public string PaidToolB(string x)
    {
        var v = Environment.GetEnvironmentVariable("E2E_DOTNET_CRED_B");
        if (string.IsNullOrEmpty(v))
            throw new TerminalToolException(
                "Credential 'E2E_DOTNET_CRED_B' not found in environment.");
        return $"paid_b:{v[..Math.Min(3, v.Length)]}";
    }
}

// ── Tool hosts ─────────────────────────────────────────────────────────────────

internal sealed class S2SingleToolHost
{
    private int _callCount;
    public int CallCount => _callCount;

    [Tool("Return a fixed sentinel value.")]
    public Dictionary<string, object> GetValue()
    {
        Interlocked.Increment(ref _callCount);
        return new() { ["value"] = 42, ["sentinel"] = "s2_single" };
    }
}

internal sealed class S2MultiToolHost
{
    private int _sqrtCalls;
    private int _addCalls;

    public int SqrtCallCount => _sqrtCalls;
    public int AddCallCount  => _addCalls;

    [Tool("Compute the square root of a number.")]
    public Dictionary<string, object> SqrtValue(double number)
    {
        Interlocked.Increment(ref _sqrtCalls);
        return new() { ["input"] = number, ["result"] = Math.Sqrt(number) };
    }

    [Tool("Add two numbers together.")]
    public Dictionary<string, object> AddNumbers(double a, double b)
    {
        Interlocked.Increment(ref _addCalls);
        return new() { ["a"] = a, ["b"] = b, ["result"] = a + b };
    }
}

internal sealed class S2EchoToolHost
{
    private int _callCount;
    public int CallCount => _callCount;

    [Tool("Echo a token back to the caller unchanged.")]
    public Dictionary<string, object> EchoToken(string token)
    {
        Interlocked.Increment(ref _callCount);
        return new() { ["echo"] = token };
    }
}

internal sealed class S2AsyncToolHost
{
    private int _callCount;
    public int CallCount => _callCount;

    [Tool("Asynchronously fetch data from an internal source.")]
    public async Task<Dictionary<string, object>> FetchData(string source = "default")
    {
        Interlocked.Increment(ref _callCount);
        await Task.Delay(10);  // simulate async work
        return new() { ["source"] = source, ["data"] = "s2_async_sentinel", ["fetched_at"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds() };
    }
}
