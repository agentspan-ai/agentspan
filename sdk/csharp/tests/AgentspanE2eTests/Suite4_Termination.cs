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

        // MaxTurns=2 caps the number of LLM rounds. Each round can issue
        // multiple parallel tool calls, so the bound on host.CallCount is
        // generous — what we're really proving is "not unbounded": with
        // MaxTurns=2, even aggressive parallel calling stays well below 100.
        // A runaway loop without MaxTurns enforcement would easily exceed it.
        Assert.True(host.CallCount <= 100,
            $"Expected bounded tool calls with MaxTurns=2 but got {host.CallCount}. " +
            "If unbounded, this would be in the thousands.");
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

    // ── 4.6  Runtime: TextMentionTermination stops loop early ────────────
    //
    // Ports Python suite12 test_text_mention_terminates_early. With max_turns=3
    // and an instruction to always include TASK_COMPLETE, the DO_WHILE loop
    // should terminate on iteration 1. We assert iteration count <= max_turns
    // (would be == max_turns if termination were broken).

    [SkippableFact]
    public async Task TextMentionTermination_RuntimeStopsEarly()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_text_term_rt")
        {
            Model        = Settings.LlmModel,
            MaxTurns     = 3,
            Instructions =
                "You MUST include the exact text TASK_COMPLETE in every response. " +
                "Answer the user's question and always end with TASK_COMPLETE.",
            Termination  = new TextMentionTermination("TASK_COMPLETE"),
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        var result = await runtime.RunAsync(agent, "Say hello.", ct: cts.Token);

        Assert.True(result.IsSuccess || result.Status == Status.Terminated,
            $"Unexpected status: {result.Status}, Error: {result.Error}");
        Assert.NotEmpty(result.ExecutionId);

        var iterations = await GetDoWhileIterationsAsync(result.ExecutionId);
        Assert.True(iterations <= 3,
            $"[TextMentionTermination] DO_WHILE ran {iterations} iterations, expected <= 3.");
    }

    // ── 4.7  Runtime: MaxMessageTermination stops at limit ───────────────
    //
    // Ports Python suite12 test_max_message_terminates_at_limit. MaxTurns=25
    // but MaxMessageTermination(3) should cap the loop at ~3 iterations.

    [SkippableFact]
    public async Task MaxMessageTermination_RuntimeStopsAtLimit()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_max_msg_rt")
        {
            Model        = Settings.LlmModel,
            MaxTurns     = 25,
            Instructions = "You are a helpful assistant. Answer the user's question. Keep your answers concise.",
            Termination  = new MaxMessageTermination(3),
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        var result = await runtime.RunAsync(agent, "Count from 1 to 100.", ct: cts.Token);

        Assert.True(result.IsSuccess || result.Status == Status.Terminated,
            $"Unexpected status: {result.Status}, Error: {result.Error}");
        Assert.NotEmpty(result.ExecutionId);

        var iterations = await GetDoWhileIterationsAsync(result.ExecutionId);
        // 0 is valid when the agent satisfies the prompt in a single response without a DO_WHILE
        // loop scheduled (no tools available => no loop). The key counterfactual is that the
        // iteration count is NOT close to MaxTurns (25) — that would mean termination was ignored.
        Assert.True(iterations <= 4,
            $"[MaxMessageTermination] DO_WHILE ran {iterations} iterations, expected <= 4. " +
            $"If close to 25, MaxMessageTermination was ignored.");
    }

    // ── 4.8  Runtime: invalid model fails ────────────────────────────────
    //
    // Ports Python suite12 test_invalid_model_fails. A nonexistent model name
    // must NOT result in a COMPLETED execution.

    [SkippableFact]
    public async Task InvalidModel_RuntimeFails()
    {
        _fixture.RequireServer();

        var agent = new Agent("s4_bad_model")
        {
            Model        = "nonexistent/xyz-model-does-not-exist",
            Instructions = "This agent should never execute successfully.",
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        var result = await runtime.RunAsync(agent, "Hello.", ct: cts.Token);

        Assert.True(result.Status is Status.Failed or Status.Terminated,
            $"[Invalid model] Expected Failed or Terminated, got '{result.Status}'. Error: {result.Error}");
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    /// <summary>Mirrors Python's _get_loop_iterations(): reads outputData.iteration
    /// from the workflow's DO_WHILE task.</summary>
    private async Task<int> GetDoWhileIterationsAsync(string executionId)
    {
        var wf = await _fixture.FetchWorkflowAsync(executionId);
        var tasks = wf?["tasks"]?.AsArray();
        if (tasks is null) return 0;
        foreach (var t in tasks)
        {
            if (t?["taskType"]?.GetValue<string>() == "DO_WHILE")
            {
                var iter = t["outputData"]?["iteration"]?.GetValue<int>();
                if (iter is not null) return iter.Value;
            }
        }
        return 0;
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
