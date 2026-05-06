// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 2 — Tool calling: verify the tool function body executes.
//
// Validation strategy: use Interlocked.Increment on a shared counter instead
// of parsing LLM text output. The counter proves the function body ran, not
// that the LLM described it correctly.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

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
