// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 13 — Stateful Domain: Agent.Stateful flag propagation to plan and local object.
//
// Corresponds to Python e2e: test_suite14_stateful_domain.py
//
// Design notes:
//   - Agent.Stateful = true propagates as stateful=true on each worker tool in the
//     serialized agentConfig sent to the server (see AgentConfigSerializer.SerializeTool).
//   - The agentDef JSON returned by PlanAsync() reflects this as stateful=true on the
//     tool entries (for worker/external tools). The agentDef itself has no top-level
//     "stateful" field — the flag lives on the tools.
//   - [Fact] tests verify Agent.Stateful property and tool-level serialization locally.
//   - [SkippableFact] tests call PlanAsync() and verify the compiled plan JSON.
//
// Two validation layers:
//   [Fact]          — pure SDK tests, no server. Inspect Agent and ToolDef properties.
//   [SkippableFact] — server tests. Verify the compiled plan's tool entries.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite13_StatefulDomain
{
    private readonly E2eFixture _fixture;

    public Suite13_StatefulDomain(E2eFixture fixture) => _fixture = fixture;

    // ── 13.1  agent.Stateful = true is reflected on the Agent object ────────
    //
    // Counterfactual: if Stateful were read-only or silently ignored, long-running
    // stateful agents could never be configured — all tool calls would miss domain routing.

    [Fact]
    public void Agent_StatefulTrue_IsReflectedOnObject()
    {
        var agent = new Agent("s13_stateful_agent")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
        };

        Assert.True(agent.Stateful);

        // Counterfactual: toggling back to false must be reflected
        agent.Stateful = false;
        Assert.False(agent.Stateful);
    }

    // ── 13.2  Default agent has Stateful=false ───────────────────────────────
    //
    // Counterfactual: if the default were true, every agent would use domain-based routing,
    // causing all tasks to pile up in a single domain queue unnecessarily.

    [Fact]
    public void Agent_DefaultStateful_IsFalse()
    {
        var agent = new Agent("s13_default_agent") { Model = Settings.LlmModel };

        Assert.False(agent.Stateful,
            "Agent.Stateful must default to false. " +
            "Enabling domain routing for all agents would cause unnecessary overhead.");

        // Counterfactual: only explicitly set agents should have Stateful=true
        var statefulAgent = new Agent("s13_explicit_stateful")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
        };
        Assert.True(statefulAgent.Stateful);
        Assert.NotEqual(agent.Stateful, statefulAgent.Stateful);
    }

    // ── 13.3  Stateful=true agent compiles — worker tools have stateful flag in plan ──
    //
    // When agent.Stateful=true, AgentConfigSerializer sets stateful=true on each
    // worker tool in the agentConfig payload. The server reflects this back in the
    // compiled plan's agentDef.tools entries.
    //
    // Counterfactual: if stateful were NOT propagated to tools, the server would never
    // assign a domain UUID and all SIMPLE tasks would stay in the default domain,
    // causing cross-execution interference for long-running agents.

    [SkippableFact]
    public async Task StatefulAgent_WorkerToolHasStatefulFlagInPlan()
    {
        _fixture.RequireServer();

        var workerTool = ToolDefFactory.Create(
            name:        "s13_stateful_worker",
            description: "A worker tool on a stateful agent",
            handler:     (_, _) => Task.FromResult<object?>("ok"));

        var agent = new Agent("s13_stateful_plan_check")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
            Tools    = [workerTool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var tool = E2eHelpers.GetTool(ad, "s13_stateful_worker");

        // Worker tool on a stateful agent must carry stateful=true
        var statefulFlag = tool["stateful"]?.GetValue<bool>();
        Assert.True(statefulFlag,
            "Worker tool on agent with Stateful=true must have stateful=true in the compiled plan. " +
            "This flag tells the server to use domain-based routing for this task.");

        // Counterfactual: agent without Stateful=true must not have stateful=true on worker tool
        var nonStatefulAgent = new Agent("s13_non_stateful_check")
        {
            Model    = Settings.LlmModel,
            Stateful = false,
            Tools    = [ToolDefFactory.Create(
                name:        "s13_regular_worker",
                description: "Regular worker tool",
                handler:     (_, _) => Task.FromResult<object?>("ok"))],
        };
        var planNs = await runtime.PlanAsync(nonStatefulAgent);
        var adNs   = E2eHelpers.GetAgentDef(planNs);
        var toolNs = E2eHelpers.GetTool(adNs, "s13_regular_worker");
        var flagNs = toolNs["stateful"]?.GetValue<bool>() ?? false;
        Assert.False(flagNs,
            "Worker tool on a non-stateful agent must NOT have stateful=true in the plan.");
    }

    // ── 13.4  Stateful=false (default) agent: plan does NOT contain stateful=true ──
    //
    // Counterfactual: if stateful defaulted to true in serialization, all agents would
    // use domain routing even when not configured — breaking multi-tenant isolation.

    [SkippableFact]
    public async Task NonStatefulAgent_WorkerToolLacksStatefulFlagInPlan()
    {
        _fixture.RequireServer();

        var workerTool = ToolDefFactory.Create(
            name:        "s13_ns_worker_check",
            description: "Worker tool on non-stateful agent",
            handler:     (_, _) => Task.FromResult<object?>("ok"));

        var agent = new Agent("s13_ns_plan_check")
        {
            Model = Settings.LlmModel,
            // Stateful is NOT set — defaults to false
            Tools = [workerTool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var tool       = E2eHelpers.GetTool(ad, "s13_ns_worker_check");
        var statefulFlag = tool["stateful"]?.GetValue<bool>() ?? false;

        Assert.False(statefulFlag,
            "Worker tool on default (non-stateful) agent must NOT have stateful=true in the plan.");

        // Counterfactual: agent with Stateful=true DOES have stateful on its tool
        var statefulAgent = new Agent("s13_s_contrast")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
            Tools    = [ToolDefFactory.Create(
                name:        "s13_s_contrast_tool",
                description: "Contrast tool",
                handler:     (_, _) => Task.FromResult<object?>("ok"))],
        };
        var planS = await runtime.PlanAsync(statefulAgent);
        var adS   = E2eHelpers.GetAgentDef(planS);
        var toolS = E2eHelpers.GetTool(adS, "s13_s_contrast_tool");
        Assert.True(toolS["stateful"]?.GetValue<bool>() ?? false,
            "Contrast: stateful agent's tool must have stateful=true.");
    }

    // ── 13.5  Stateful agent with tools: both stateful flag and tools present in plan ──
    //
    // Verifies that a stateful agent with multiple tools compiles correctly and
    // all worker tools receive the stateful=true marker.
    //
    // Counterfactual: if only the first tool received the flag, subsequent tools
    // would execute in the default domain and miss domain routing entirely.

    [SkippableFact]
    public async Task StatefulAgentWithMultipleTools_AllWorkerToolsHaveStatefulFlag()
    {
        _fixture.RequireServer();

        var tool1 = ToolDefFactory.Create(
            name:        "s13_multi_tool_a",
            description: "First worker tool",
            handler:     (_, _) => Task.FromResult<object?>("a"));

        var tool2 = ToolDefFactory.Create(
            name:        "s13_multi_tool_b",
            description: "Second worker tool",
            handler:     (_, _) => Task.FromResult<object?>("b"));

        var agent = new Agent("s13_multi_stateful")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
            Tools    = [tool1, tool2],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var toolNames = E2eHelpers.ToolNames(ad);
        Assert.Contains("s13_multi_tool_a", toolNames);
        Assert.Contains("s13_multi_tool_b", toolNames);

        // Both worker tools must carry stateful=true
        var toolA = E2eHelpers.GetTool(ad, "s13_multi_tool_a");
        var toolB = E2eHelpers.GetTool(ad, "s13_multi_tool_b");

        Assert.True(toolA["stateful"]?.GetValue<bool>() ?? false,
            "First tool on stateful agent must have stateful=true.");
        Assert.True(toolB["stateful"]?.GetValue<bool>() ?? false,
            "Second tool on stateful agent must have stateful=true.");

        // Counterfactual: an HTTP tool on a stateful agent must NOT have stateful=true
        // (HTTP tools run server-side and do not use domain routing)
        var httpTool = HttpTools.Create(
            name:        "s13_http_on_stateful",
            description: "HTTP tool on a stateful agent",
            url:         "https://api.example.com/data",
            method:      "GET");

        var agentMixed = new Agent("s13_mixed_stateful")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
            Tools    = [tool1, httpTool],
        };
        var planMixed = await runtime.PlanAsync(agentMixed);
        var adMixed   = E2eHelpers.GetAgentDef(planMixed);

        var httpToolNode = E2eHelpers.GetTool(adMixed, "s13_http_on_stateful");
        var httpStateful = httpToolNode["stateful"]?.GetValue<bool>() ?? false;
        Assert.False(httpStateful,
            "HTTP tool (server-side) on stateful agent must NOT have stateful=true — " +
            "domain routing applies only to worker/external tools.");
    }

    // ── 13.6  Two stateful agents: each compiles independently with their own stateful flag ──
    //
    // Verifies that multiple stateful agents can be compiled independently without
    // one affecting the other's plan.
    //
    // Counterfactual: if Agent.Stateful were a static/shared field, the second
    // agent's compilation could override the first's stateful state.

    [SkippableFact]
    public async Task TwoStatefulAgents_CompileIndependently()
    {
        _fixture.RequireServer();

        var toolA = ToolDefFactory.Create(
            name:        "s13_agent_a_tool",
            description: "Tool for agent A",
            handler:     (_, _) => Task.FromResult<object?>("a_result"));

        var toolB = ToolDefFactory.Create(
            name:        "s13_agent_b_tool",
            description: "Tool for agent B",
            handler:     (_, _) => Task.FromResult<object?>("b_result"));

        var agentA = new Agent("s13_stateful_a")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
            Tools    = [toolA],
        };

        var agentB = new Agent("s13_stateful_b")
        {
            Model    = Settings.LlmModel,
            Stateful = true,
            Tools    = [toolB],
        };

        await using var runtime = new AgentRuntime();

        var planA = await runtime.PlanAsync(agentA);
        var planB = await runtime.PlanAsync(agentB);

        var adA = E2eHelpers.GetAgentDef(planA);
        var adB = E2eHelpers.GetAgentDef(planB);

        // Agent A's plan has tool A with stateful=true
        var nodeA = E2eHelpers.GetTool(adA, "s13_agent_a_tool");
        Assert.True(nodeA["stateful"]?.GetValue<bool>() ?? false,
            "Agent A's tool must have stateful=true in its plan.");
        Assert.DoesNotContain("s13_agent_b_tool", E2eHelpers.ToolNames(adA));

        // Agent B's plan has tool B with stateful=true
        var nodeB = E2eHelpers.GetTool(adB, "s13_agent_b_tool");
        Assert.True(nodeB["stateful"]?.GetValue<bool>() ?? false,
            "Agent B's tool must have stateful=true in its plan.");
        Assert.DoesNotContain("s13_agent_a_tool", E2eHelpers.ToolNames(adB));

        // Counterfactual: each plan names only its own agent
        var nameA = adA["name"]?.GetValue<string>();
        var nameB = adB["name"]?.GetValue<string>();
        Assert.NotEqual(nameA, nameB);
        Assert.Equal("s13_stateful_a", nameA);
        Assert.Equal("s13_stateful_b", nameB);
    }
}
