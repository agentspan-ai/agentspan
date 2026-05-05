// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 5 — Multi-agent strategies: structural plan validation.
//
// All tests use PlanAsync() — no execution, no LLM calls.
// We verify that the compiled workflow reflects the intended strategy, sub-agent
// list, and task shape.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite5_Strategies
{
    private readonly E2eFixture _fixture;

    public Suite5_Strategies(E2eFixture fixture) => _fixture = fixture;

    // ── 5.1  Handoff strategy ────────────────────────────────────────────

    [SkippableFact]
    public async Task HandoffStrategy_CompilesCorrectly()
    {
        _fixture.RequireServer();

        var child1 = new Agent("s5_child_a") { Model = Settings.LlmModel, Instructions = "Child A." };
        var child2 = new Agent("s5_child_b") { Model = Settings.LlmModel, Instructions = "Child B." };

        var parent = new Agent("s5_handoff")
        {
            Model        = Settings.LlmModel,
            Instructions = "Route to child_a or child_b.",
            Agents       = [child1, child2],
            Strategy     = Strategy.Handoff,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(parent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.Equal("handoff", strategy, ignoreCase: true);

        // Counterfactual: sequential has different strategy value
        var seqParent = new Agent("s5_seq_check")
        {
            Model    = Settings.LlmModel,
            Agents   = [child1, child2],
            Strategy = Strategy.Sequential,
        };
        var planSeq = await runtime.PlanAsync(seqParent);
        var seqStrategy = planSeq?["workflowDef"]?["metadata"]?["agentDef"]?["strategy"]?.GetValue<string>();
        Assert.NotEqual("handoff", seqStrategy, StringComparer.OrdinalIgnoreCase);
    }

    // ── 5.2  Sequential strategy ─────────────────────────────────────────

    [SkippableFact]
    public async Task SequentialStrategy_CompilesCorrectly()
    {
        _fixture.RequireServer();

        var step1 = new Agent("s5_step1") { Model = Settings.LlmModel, Instructions = "Step 1." };
        var step2 = new Agent("s5_step2") { Model = Settings.LlmModel, Instructions = "Step 2." };

        var pipeline = new Agent("s5_sequential")
        {
            Model    = Settings.LlmModel,
            Agents   = [step1, step2],
            Strategy = Strategy.Sequential,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(pipeline);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.Equal("sequential", strategy, ignoreCase: true);

        // Two sub-agents must be listed
        var agents = agentDef["agents"]?.AsArray() ?? agentDef["subAgents"]?.AsArray();
        Assert.NotNull(agents);
        Assert.Equal(2, agents!.Count);
    }

    // ── 5.3  Parallel strategy ───────────────────────────────────────────

    [SkippableFact]
    public async Task ParallelStrategy_CompilesCorrectly()
    {
        _fixture.RequireServer();

        var branch1 = new Agent("s5_branch1") { Model = Settings.LlmModel, Instructions = "Branch 1." };
        var branch2 = new Agent("s5_branch2") { Model = Settings.LlmModel, Instructions = "Branch 2." };
        var branch3 = new Agent("s5_branch3") { Model = Settings.LlmModel, Instructions = "Branch 3." };

        var parent = new Agent("s5_parallel")
        {
            Model    = Settings.LlmModel,
            Agents   = [branch1, branch2, branch3],
            Strategy = Strategy.Parallel,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(parent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.Equal("parallel", strategy, ignoreCase: true);

        // Three sub-agents
        var agents = agentDef["agents"]?.AsArray() ?? agentDef["subAgents"]?.AsArray();
        Assert.NotNull(agents);
        Assert.Equal(3, agents!.Count);
    }

    // ── 5.4  Swarm strategy ──────────────────────────────────────────────

    [SkippableFact]
    public async Task SwarmStrategy_CompilesCorrectly()
    {
        _fixture.RequireServer();

        var worker1 = new Agent("s5_swarm1") { Model = Settings.LlmModel, Instructions = "Worker 1." };
        var worker2 = new Agent("s5_swarm2") { Model = Settings.LlmModel, Instructions = "Worker 2." };

        var swarm = new Agent("s5_swarm")
        {
            Model    = Settings.LlmModel,
            Agents   = [worker1, worker2],
            Strategy = Strategy.Swarm,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(swarm);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.Equal("swarm", strategy, ignoreCase: true);
    }

    // ── 5.5  >> operator creates sequential pipeline ─────────────────────

    [SkippableFact]
    public async Task PipelineOperator_CreatesSequentialPlan()
    {
        _fixture.RequireServer();

        var step1 = new Agent("s5_op_step1") { Model = Settings.LlmModel, Instructions = "Step 1." };
        var step2 = new Agent("s5_op_step2") { Model = Settings.LlmModel, Instructions = "Step 2." };
        var step3 = new Agent("s5_op_step3") { Model = Settings.LlmModel, Instructions = "Step 3." };

        var pipeline = step1 >> step2 >> step3;

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(pipeline);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.Equal("sequential", strategy, ignoreCase: true);

        // All three steps must appear
        var agents = agentDef["agents"]?.AsArray() ?? agentDef["subAgents"]?.AsArray();
        Assert.NotNull(agents);
        Assert.True(agents!.Count >= 3, $"Expected >= 3 sub-agents but got {agents.Count}.");
    }

    // ── 5.6  Router strategy ─────────────────────────────────────────────

    [SkippableFact]
    public async Task RouterStrategy_CompilesCorrectly()
    {
        _fixture.RequireServer();

        var routerAgent = new Agent("s5_router_llm")
        {
            Model        = Settings.LlmModel,
            Instructions = "Decide which agent to route to.",
        };

        var target1 = new Agent("s5_route_t1") { Model = Settings.LlmModel, Instructions = "Handle A." };
        var target2 = new Agent("s5_route_t2") { Model = Settings.LlmModel, Instructions = "Handle B." };

        var parent = new Agent("s5_router")
        {
            Model    = Settings.LlmModel,
            Agents   = [target1, target2],
            Strategy = Strategy.Router,
            Router   = routerAgent,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(parent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.Equal("router", strategy, ignoreCase: true);
    }
}
