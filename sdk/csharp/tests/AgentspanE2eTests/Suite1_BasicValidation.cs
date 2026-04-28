// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 1 — Basic plan/structural validation.
//
// All tests use PlanAsync() — no execution, no LLM calls.
// Assertions are structural: workflow shape, tool names, guardrail fields,
// strategy values, termination conditions.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite1_BasicValidation
{
    private readonly E2eFixture _fixture;

    public Suite1_BasicValidation(E2eFixture fixture) => _fixture = fixture;

    // ── 1.1  Basic agent compiles ────────────────────────────────────────

    [SkippableFact]
    public async Task BasicAgent_CompilesSuccessfully()
    {
        _fixture.RequireServer();

        var agent = new Agent("s1_basic_test")
        {
            Model        = Settings.LlmModel,
            Instructions = "You are a friendly assistant.",
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        // workflowDef must be present
        Assert.NotNull(plan);
        Assert.NotNull(plan!["workflowDef"]);

        // workflow name should contain the agent name
        var name = plan["workflowDef"]!["name"]?.GetValue<string>();
        Assert.NotNull(name);
        Assert.Contains("s1_basic_test", name);

        // at least one task must exist
        var tasks = plan["workflowDef"]!["tasks"]?.AsArray();
        Assert.NotNull(tasks);
        Assert.True(tasks!.Count > 0, "Expected at least one task in compiled workflow.");
    }

    // ── 1.2  Tool names present in agentDef.tools ───────────────────────

    [SkippableFact]
    public async Task ToolAgent_ToolNamesInAgentDef()
    {
        _fixture.RequireServer();

        var tools = ToolRegistry.FromInstance(new S1ToolHost());
        var agent = new Agent("s1_tool_test")
        {
            Model        = Settings.LlmModel,
            Instructions = "Use tools to answer.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);

        // Tools are listed in plan["workflowDef"]["metadata"]["agentDef"]["tools"]
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"]
                       ?? throw new InvalidOperationException("agentDef missing from plan metadata.");
        var toolsArray = agentDef["tools"]?.AsArray()
                         ?? throw new InvalidOperationException("tools missing from agentDef.");

        var toolNames = toolsArray.Select(t => t?["name"]?.GetValue<string>() ?? "").ToList();

        // Both tools must be listed in the agent definition
        Assert.Contains(toolNames, n => n.Equals("get_greeting", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(toolNames, n => n.Equals("get_farewell", StringComparison.OrdinalIgnoreCase));

        // Counterfactual: a tool that does NOT exist must NOT appear
        Assert.DoesNotContain(toolNames, n => n.Contains("nonexistent_tool_xyz", StringComparison.OrdinalIgnoreCase));
    }

    // ── 1.3  Guardrail fields present in agentDef ────────────────────────

    [SkippableFact]
    public async Task GuardrailAgent_GuardrailFieldsInPlan()
    {
        _fixture.RequireServer();

        var guardrailHost = new S1GuardrailHost();
        var guardrails    = GuardrailRegistry.FromInstance(guardrailHost);

        var agent = new Agent("s1_guardrail_test")
        {
            Model      = Settings.LlmModel,
            Instructions = "You are a helpful agent.",
            Guardrails = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);

        // agentDef is nested inside the plan's metadata
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        // guardrails array must be non-empty
        var guardrailArr = agentDef!["guardrails"]?.AsArray();
        Assert.NotNull(guardrailArr);
        Assert.True(guardrailArr!.Count > 0, "Expected at least one guardrail in agentDef.");

        // Counterfactual: an agent without guardrails must have an empty array or null
        var agentNoGuardrail = new Agent("s1_no_guardrail_test") { Model = Settings.LlmModel };
        var planNoGuardrail  = await runtime.PlanAsync(agentNoGuardrail);
        var noGuardrailDef   = planNoGuardrail?["workflowDef"]?["metadata"]?["agentDef"];
        var noGuardrailArr   = noGuardrailDef?["guardrails"]?.AsArray();
        Assert.True(noGuardrailArr is null || noGuardrailArr.Count == 0,
            "Agent without guardrails must have no guardrail entries in plan.");
    }

    // ── 1.4  Strategy serialised correctly for multi-agent plans ─────────

    [SkippableFact]
    public async Task HandoffAgent_StrategyInPlan()
    {
        _fixture.RequireServer();

        var child1 = new Agent("s1_billing") { Model = Settings.LlmModel, Instructions = "Handle billing." };
        var child2 = new Agent("s1_tech")    { Model = Settings.LlmModel, Instructions = "Handle tech." };

        var parent = new Agent("s1_handoff_test")
        {
            Model        = Settings.LlmModel,
            Instructions = "Route to billing or tech.",
            Agents       = [child1, child2],
            Strategy     = Strategy.Handoff,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(parent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var strategy = agentDef!["strategy"]?.GetValue<string>();
        Assert.NotNull(strategy);
        Assert.Equal("handoff", strategy, ignoreCase: true);

        // sub-agents must be listed
        var subAgents = agentDef["agents"]?.AsArray()
                        ?? agentDef["subAgents"]?.AsArray();
        Assert.NotNull(subAgents);
        Assert.True(subAgents!.Count >= 2, "Expected at least 2 sub-agents in plan.");
    }

    // ── 1.5  MaxTurns serialised in agentDef ────────────────────────────

    [SkippableFact]
    public async Task AgentWithMaxTurns_MaxTurnsInPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s1_maxturn_test")
        {
            Model    = Settings.LlmModel,
            MaxTurns = 7,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        var maxTurns = agentDef!["maxTurns"]?.GetValue<int>();
        Assert.Equal(7, maxTurns);

        // Counterfactual: different MaxTurns must serialize to different value
        var agent2  = new Agent("s1_maxturn_test2") { Model = Settings.LlmModel, MaxTurns = 3 };
        var plan2   = await runtime.PlanAsync(agent2);
        var maxTurns2 = plan2?["workflowDef"]?["metadata"]?["agentDef"]?["maxTurns"]?.GetValue<int>();
        Assert.NotEqual(7, maxTurns2);
    }

    // ── 1.6  Termination condition serialised ────────────────────────────

    [SkippableFact]
    public async Task AgentWithTermination_TerminationInPlan()
    {
        _fixture.RequireServer();

        var agent = new Agent("s1_termination_test")
        {
            Model       = Settings.LlmModel,
            Termination = new TextMentionTermination("DONE"),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        var agentDef = plan!["workflowDef"]?["metadata"]?["agentDef"];
        Assert.NotNull(agentDef);

        // termination config must exist
        var termination = agentDef!["termination"];
        Assert.NotNull(termination);

        // Counterfactual: agent without termination must not have a termination block
        var agentNoTerm = new Agent("s1_no_term_test") { Model = Settings.LlmModel };
        var planNoTerm  = await runtime.PlanAsync(agentNoTerm);
        var noTermDef   = planNoTerm?["workflowDef"]?["metadata"]?["agentDef"];
        var noTerm      = noTermDef?["termination"];
        Assert.Null(noTerm);
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

internal sealed class S1ToolHost
{
    [Tool("Return a greeting for a name.")]
    public string GetGreeting(string name) => $"Hello, {name}!";

    [Tool("Return a farewell for a name.")]
    public string GetFarewell(string name) => $"Goodbye, {name}!";
}

internal sealed class S1GuardrailHost
{
    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 2)]
    public GuardrailResult NoAllCaps(string content)
        => new(content != content.ToUpper(), "Response must not be ALL CAPS.");
}
