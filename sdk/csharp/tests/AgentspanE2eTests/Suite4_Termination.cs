// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 4 — Termination conditions.
//
// Tests verify that the server honours termination configs: the agent stops
// when the condition fires and the execution status is Completed (not Failed).
//
// Validation: Plan structure (no LLM call) for config, and IsSuccess for
// execution tests. We do not parse LLM text.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite4_Termination
{
    private readonly E2eFixture _fixture;

    public Suite4_Termination(E2eFixture fixture) => _fixture = fixture;

    // ── 4.1  MaxMessageTermination serialised in plan ────────────────────

    [SkippableFact]
    public async Task MaxMessageTermination_InPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_max_msg_plan")
        {
            Model       = Settings.LlmModel,
            Termination = new MaxMessageTermination(3),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);
        Assert.NotNull(agentDef!["termination"]);
    }

    // ── 4.2  TextMentionTermination serialised in plan ───────────────────

    [SkippableFact]
    public async Task TextMentionTermination_InPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_text_mention_plan")
        {
            Model       = Settings.LlmModel,
            Termination = new TextMentionTermination("DONE"),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var termination = agentDef!["termination"];
        Assert.NotNull(termination);

        // Counterfactual: agent without termination has null termination block
        var agentNoTerm = new Agent("s4_no_term") { Model = Settings.LlmModel };
        var planNoTerm  = await runtime.PlanAsync(agentNoTerm);
        var noTerm      = planNoTerm?["workflowDef"]?["metadata"]?["agentDef"]?["termination"];
        Assert.Null(noTerm);
    }

    // ── 4.3  StopMessageTermination serialised in plan ───────────────────

    [SkippableFact]
    public async Task StopMessageTermination_InPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_stop_msg_plan")
        {
            Model       = Settings.LlmModel,
            Termination = new StopMessageTermination("TERMINATE"),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);
        Assert.NotNull(agentDef!["termination"]);
    }

    // ── 4.4  MaxTurns respected at runtime ───────────────────────────────

    [SkippableFact]
    public async Task MaxTurns_AgentDoesNotRunForever()
    {
        _fixture.RequireServer();

        var host  = new S4CountingToolHost();
        var tools = ToolRegistry.FromInstance(host);

        // MaxTurns = 2 caps how many LLM rounds can happen
        var agent = new Agent("s4_max_turns")
        {
            Model        = Settings.LlmModel,
            Instructions = "You MUST call count_turn on every message, then respond.",
            Tools        = tools,
            MaxTurns     = 2,
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        var result = await runtime.RunAsync(agent, "Keep calling count_turn repeatedly.", ct: cts.Token);

        // The agent must complete (not time out or fail with a system error)
        Assert.True(result.IsSuccess || result.Status == Status.Terminated,
            $"Unexpected status: {result.Status}, Error: {result.Error}");

        // MaxTurns=2 means the tool can only be called a bounded number of times
        Assert.True(host.CallCount <= 10,
            $"Expected bounded tool calls with MaxTurns=2 but got {host.CallCount}.");
    }

    // ── 4.5  Composable termination: OR of two conditions ────────────────

    [SkippableFact]
    public async Task ComposedOrTermination_InPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_composed_term")
        {
            Model       = Settings.LlmModel,
            Termination = new TextMentionTermination("DONE") | new MaxMessageTermination(5),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);
        Assert.NotNull(agentDef!["termination"]);
    }
}

// ── Tool hosts ─────────────────────────────────────────────────────────────────

internal sealed class S4CountingToolHost
{
    private int _callCount;
    public int CallCount => _callCount;

    [Tool("Count how many times this tool has been called.")]
    public Dictionary<string, object> CountTurn()
    {
        var count = System.Threading.Interlocked.Increment(ref _callCount);
        return new() { ["turn"] = count };
    }
}
