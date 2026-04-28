// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 6 — Callbacks: verify BeforeModelCallback and AfterModelCallback
// function bodies execute during an agent run.
//
// IMPORTANT: callbacks only run when the agent compiles to a DO_WHILE loop,
// which requires at least one tool. Simple agents without tools compile to a
// single LLM_CHAT_COMPLETE task where no local callback workers are invoked.
// All tests here include a tool to ensure the callback workers are dispatched.
//
// Validation: thread-safe counters incremented inside each callback.
// We do NOT inspect LLM text output.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.Json;
using System.Threading;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite6_Callbacks
{
    private readonly E2eFixture _fixture;

    public Suite6_Callbacks(E2eFixture fixture) => _fixture = fixture;

    // ── 6.1  BeforeModelCallback fires ───────────────────────────────────

    [SkippableFact]
    public async Task BeforeModelCallback_FunctionBodyExecutes()
    {
        _fixture.RequireServer();

        int beforeCount = 0;
        var toolHost    = new S6NoopToolHost();
        var tools       = ToolRegistry.FromInstance(toolHost);

        // Agent MUST have a tool so the server compiles a DO_WHILE loop
        // (simple agents without tools compile to a plain LLM_CHAT_COMPLETE
        //  task where callback workers are never dispatched).
        var agent = new Agent("s6_before_callback")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call noop_ping before answering. Do not skip it.",
            Tools        = tools,

            BeforeModelCallback = messages =>
            {
                Interlocked.Increment(ref beforeCount);
                return [];  // empty = let LLM proceed normally
            },
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Ping and then say hello.");

        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
        Assert.True(beforeCount > 0,
            $"BeforeModelCallback never executed. Count={beforeCount}.");
    }

    // ── 6.2  AfterModelCallback fires ─────────────────────────────────────

    [SkippableFact]
    public async Task AfterModelCallback_FunctionBodyExecutes()
    {
        _fixture.RequireServer();

        int afterCount = 0;
        var toolHost   = new S6NoopToolHost();
        var tools      = ToolRegistry.FromInstance(toolHost);

        var agent = new Agent("s6_after_callback")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call noop_ping before answering.",
            Tools        = tools,

            AfterModelCallback = llmResult =>
            {
                Interlocked.Increment(ref afterCount);
                return [];  // empty = keep original response
            },
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Ping then say hello.");

        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
        Assert.True(afterCount > 0,
            $"AfterModelCallback never executed. Count={afterCount}.");
    }

    // ── 6.3  Both callbacks fire in the same agent ────────────────────────

    [SkippableFact]
    public async Task BothCallbacks_BothFire()
    {
        _fixture.RequireServer();

        int beforeCount = 0;
        int afterCount  = 0;
        var toolHost    = new S6NoopToolHost();
        var tools       = ToolRegistry.FromInstance(toolHost);

        var agent = new Agent("s6_both_callbacks")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call noop_ping before answering.",
            Tools        = tools,

            BeforeModelCallback = _ =>
            {
                Interlocked.Increment(ref beforeCount);
                return [];
            },

            AfterModelCallback = _ =>
            {
                Interlocked.Increment(ref afterCount);
                return [];
            },
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Ping once then say hi.");

        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
        Assert.True(beforeCount > 0, $"BeforeModelCallback never fired. Count={beforeCount}.");
        Assert.True(afterCount  > 0, $"AfterModelCallback never fired. Count={afterCount}.");
    }

    // ── 6.4  Callback + tool: callback fires when tools are used ─────────

    [SkippableFact]
    public async Task CallbackWithTool_CallbackFiresAroundToolCalls()
    {
        _fixture.RequireServer();

        int beforeCount = 0;
        var toolHost    = new S6DataToolHost();
        var tools       = ToolRegistry.FromInstance(toolHost);

        var agent = new Agent("s6_callback_tool")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call get_data and then answer.",
            Tools        = tools,

            BeforeModelCallback = _ =>
            {
                Interlocked.Increment(ref beforeCount);
                return [];
            },
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Get some data and summarize it.");

        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");

        // Tool must have been called
        Assert.True(toolHost.CallCount > 0,
            $"Expected get_data to be called but CallCount={toolHost.CallCount}.");

        // BeforeModelCallback must have fired at least once
        Assert.True(beforeCount > 0,
            $"BeforeModelCallback never fired. Count={beforeCount}.");
    }

    // ── 6.5  Callback serialised in plan ─────────────────────────────────

    [SkippableFact]
    public async Task CallbackAgent_CompilesWithCallbacksInPlan()
    {
        _fixture.RequireServer();

        var tools = ToolRegistry.FromInstance(new S6NoopToolHost());

        var agent = new Agent("s6_callback_plan")
        {
            Model        = Settings.LlmModel,
            Instructions = "Answer briefly.",
            Tools        = tools,
            BeforeModelCallback = _ => [],
            AfterModelCallback  = _ => [],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        // The workflow must compile successfully (plan is non-null with a workflowDef)
        Assert.NotNull(plan!["workflowDef"]);
        Assert.NotNull(plan["workflowDef"]!["name"]);

        // Callbacks must appear in the agentDef metadata
        var agentDef  = plan["workflowDef"]!["metadata"]?["agentDef"];
        var callbacks = agentDef?["callbacks"]?.AsArray();
        Assert.NotNull(callbacks);
        Assert.True(callbacks!.Count >= 2, $"Expected at least 2 callbacks in plan but got {callbacks.Count}.");

        // Counterfactual: agent without callbacks compiles too (regression check)
        var agentNoCallbacks = new Agent("s6_no_callback_plan")
        {
            Model = Settings.LlmModel,
            Tools = ToolRegistry.FromInstance(new S6NoopToolHost()),
        };
        var planNoCallbacks  = await runtime.PlanAsync(agentNoCallbacks);
        Assert.NotNull(planNoCallbacks?["workflowDef"]);

        var noCallbacksArr = planNoCallbacks?["workflowDef"]?["metadata"]?["agentDef"]?["callbacks"]?.AsArray();
        Assert.True(noCallbacksArr is null || noCallbacksArr.Count == 0,
            "Agent without callbacks must have no callbacks in plan.");
    }
}

// ── Tool hosts ─────────────────────────────────────────────────────────────────

/// <summary>
/// Minimal tool that makes the server compile the agent to a DO_WHILE loop
/// (required for callback workers to be dispatched).
/// </summary>
internal sealed class S6NoopToolHost
{
    [Tool("Ping — no-op tool used to force DO_WHILE compilation.")]
    public Dictionary<string, object> NoopPing()
        => new() { ["pong"] = true };
}

internal sealed class S6DataToolHost
{
    private int _callCount;
    public int CallCount => _callCount;

    [Tool("Fetch some data.")]
    public Dictionary<string, object> GetData()
    {
        Interlocked.Increment(ref _callCount);
        return new() { ["data"] = "s6_sentinel", ["timestamp"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds() };
    }
}
