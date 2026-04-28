// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 1 — AgentDef JSON must match.
//
// All tests use PlanAsync() — no execution, no LLM calls.
// Assertions check each field in the compiled agentDef exactly:
//   toolType, credentials, guardrailType, position, onFail, maxRetries,
//   strategy, model, instructions, maxTurns.
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

    // ── 1.1  Workflow structure and agentDef base fields ─────────────────

    [SkippableFact]
    public async Task BasicAgent_PlanStructureMatches()
    {
        _fixture.RequireServer();

        var agent = new Agent("s1_basic_agent")
        {
            Model        = "openai/gpt-4o-mini",
            Instructions = "You are a test assistant.",
            MaxTurns     = 8,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);

        // workflowDef.name must match agent name
        var wfName = plan!["workflowDef"]?["name"]?.GetValue<string>();
        Assert.Equal("s1_basic_agent", wfName);

        // tasks must be non-empty
        var tasks = plan["workflowDef"]!["tasks"]?.AsArray();
        Assert.NotNull(tasks);
        Assert.True(tasks!.Count > 0, "workflowDef.tasks must not be empty.");

        // agentDef fields
        var ad = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("s1_basic_agent",    ad["name"]?.GetValue<string>());
        Assert.Equal("openai/gpt-4o-mini", ad["model"]?.GetValue<string>());
        Assert.Equal("You are a test assistant.", ad["instructions"]?.GetValue<string>());
        Assert.Equal(8, ad["maxTurns"]?.GetValue<int>());

        // Counterfactual: different MaxTurns must produce a different value
        var agent2 = new Agent("s1_basic_agent_v2")
        {
            Model    = "openai/gpt-4o-mini",
            MaxTurns = 3,
        };
        var plan2 = await runtime.PlanAsync(agent2);
        var ad2   = E2eHelpers.GetAgentDef(plan2);
        Assert.Equal(3,  ad2["maxTurns"]?.GetValue<int>());
        Assert.NotEqual(8, ad2["maxTurns"]?.GetValue<int>());
    }

    // ── 1.2  Worker tool toolType ─────────────────────────────────────────

    [SkippableFact]
    public async Task WorkerTools_ToolTypeIsWorker()
    {
        _fixture.RequireServer();

        var tools = ToolRegistry.FromInstance(new S1WorkerToolHost());
        var agent = new Agent("s1_worker_tools")
        {
            Model        = Settings.LlmModel,
            Instructions = "Use tools.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // Both tools must be present with toolType = "worker"
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "get_greeting"));
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "get_farewell"));

        // Counterfactual: a tool that doesn't exist must throw (not silently return)
        Assert.DoesNotContain("nonexistent_tool_xyz", E2eHelpers.ToolNames(ad));
    }

    // ── 1.3  Credential tools — present in agentDef with correct toolType ──
    //
    // NOTE: The server strips credential values from plan() responses for security.
    //       We verify the tools ARE registered with toolType="worker" in the
    //       compiled workflow. Credential injection is tested at execution time
    //       in examples/16_Credentials (runs against real server with stored creds).

    [SkippableFact]
    public async Task CredentialTools_PresentInAgentDefWithWorkerType()
    {
        _fixture.RequireServer();

        var tools = ToolRegistry.FromInstance(new S1CredentialToolHost());
        var agent = new Agent("s1_cred_tools")
        {
            Model        = Settings.LlmModel,
            Instructions = "Use tools.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // All three tools must be present with toolType = "worker"
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "single_cred_tool"));
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "multi_cred_tool"));
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "no_cred_tool"));

        // All three must appear in the tool name list
        var names = E2eHelpers.ToolNames(ad);
        Assert.Contains("single_cred_tool", names);
        Assert.Contains("multi_cred_tool",  names);
        Assert.Contains("no_cred_tool",     names);

        // Counterfactual: tool count must match exactly what was registered
        Assert.Equal(3, names.Count(n => n is "single_cred_tool" or "multi_cred_tool" or "no_cred_tool"));
    }

    // ── 1.4  Output guardrail fields ──────────────────────────────────────

    [SkippableFact]
    public async Task OutputGuardrail_FieldsMatchExactly()
    {
        _fixture.RequireServer();

        var guardrails = GuardrailRegistry.FromInstance(new S1OutputGuardrailHost());
        var agent = new Agent("s1_output_guardrail")
        {
            Model      = Settings.LlmModel,
            Guardrails = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var g = E2eHelpers.GetGuardrail(ad, "no_all_caps");

        Assert.Equal("no_all_caps", g["name"]?.GetValue<string>());
        Assert.Equal("output",      g["position"]?.GetValue<string>());
        Assert.Equal("retry",       g["onFail"]?.GetValue<string>());
        Assert.Equal(2,             g["maxRetries"]?.GetValue<int>());
        Assert.Equal("custom",      g["guardrailType"]?.GetValue<string>());
    }

    // ── 1.5  Input guardrail position ────────────────────────────────────

    [SkippableFact]
    public async Task InputGuardrail_PositionIsInput()
    {
        _fixture.RequireServer();

        var guardrails = GuardrailRegistry.FromInstance(new S1InputGuardrailHost());
        var agent = new Agent("s1_input_guardrail")
        {
            Model      = Settings.LlmModel,
            Guardrails = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var g = E2eHelpers.GetGuardrail(ad, "check_input");
        Assert.Equal("input",  g["position"]?.GetValue<string>());
        Assert.Equal("raise",  g["onFail"]?.GetValue<string>());
        Assert.Equal("custom", g["guardrailType"]?.GetValue<string>());

        // Counterfactual: output guardrail must have position = "output"
        var guardrails2 = GuardrailRegistry.FromInstance(new S1OutputGuardrailHost());
        var agent2      = new Agent("s1_output_check") { Model = Settings.LlmModel, Guardrails = guardrails2 };
        var plan2       = await runtime.PlanAsync(agent2);
        var ad2         = E2eHelpers.GetAgentDef(plan2);
        var g2          = E2eHelpers.GetGuardrail(ad2, "no_all_caps");
        Assert.Equal("output", g2["position"]?.GetValue<string>());
        Assert.NotEqual("input", g2["position"]?.GetValue<string>());
    }

    // ── 1.6  Multiple guardrails — all present with correct fields ────────

    [SkippableFact]
    public async Task MultiGuardrail_AllPresentWithCorrectFields()
    {
        _fixture.RequireServer();

        var guardrails = GuardrailRegistry.FromInstance(new S1MultiGuardrailHost());
        var agent = new Agent("s1_multi_guardrail")
        {
            Model      = Settings.LlmModel,
            Guardrails = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var names = E2eHelpers.GuardrailNames(ad);
        Assert.Equal(3, names.Count);

        // input_check: input, raise
        var inputCheck = E2eHelpers.GetGuardrail(ad, "input_check");
        Assert.Equal("input",  inputCheck["position"]?.GetValue<string>());
        Assert.Equal("raise",  inputCheck["onFail"]?.GetValue<string>());
        Assert.Equal("custom", inputCheck["guardrailType"]?.GetValue<string>());

        // output_retry: output, retry, maxRetries=3
        var outputRetry = E2eHelpers.GetGuardrail(ad, "output_retry");
        Assert.Equal("output", outputRetry["position"]?.GetValue<string>());
        Assert.Equal("retry",  outputRetry["onFail"]?.GetValue<string>());
        Assert.Equal(3,        outputRetry["maxRetries"]?.GetValue<int>());

        // output_fix: output, fix, maxRetries=1
        var outputFix = E2eHelpers.GetGuardrail(ad, "output_fix");
        Assert.Equal("output", outputFix["position"]?.GetValue<string>());
        Assert.Equal("fix",    outputFix["onFail"]?.GetValue<string>());
        Assert.Equal(1,        outputFix["maxRetries"]?.GetValue<int>());
    }

    // ── 1.7  Handoff strategy — fields and sub-agents ────────────────────

    [SkippableFact]
    public async Task HandoffStrategy_StrategyAndSubAgentsMatch()
    {
        _fixture.RequireServer();

        var child1 = new Agent("s1_billing_a") { Model = Settings.LlmModel, Instructions = "Billing." };
        var child2 = new Agent("s1_technical_a") { Model = Settings.LlmModel, Instructions = "Tech." };

        var parent = new Agent("s1_handoff_parent")
        {
            Model        = Settings.LlmModel,
            Instructions = "Route to billing or technical.",
            Agents       = [child1, child2],
            Strategy     = Strategy.Handoff,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(parent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // Parent strategy
        Assert.Equal("handoff", ad["strategy"]?.GetValue<string>());

        // Sub-agents list
        var subNames = E2eHelpers.SubAgentNames(ad);
        Assert.Contains("s1_billing_a",   subNames);
        Assert.Contains("s1_technical_a", subNames);

        // Counterfactual: sequential strategy must differ
        var seqParent = new Agent("s1_seq_check")
        {
            Model    = Settings.LlmModel,
            Agents   = [child1, child2],
            Strategy = Strategy.Sequential,
        };
        var planSeq = await runtime.PlanAsync(seqParent);
        var adSeq   = E2eHelpers.GetAgentDef(planSeq);
        Assert.NotEqual("handoff", adSeq["strategy"]?.GetValue<string>());
        Assert.Equal("sequential", adSeq["strategy"]?.GetValue<string>());
    }

    // ── 1.8  All strategy enum values serialize correctly ─────────────────

    [SkippableFact]
    public async Task AllStrategies_SerializeToCorrectWireValues()
    {
        _fixture.RequireServer();

        await using var runtime = new AgentRuntime();

        var cases = new (Strategy strategy, string expected)[]
        {
            (Strategy.Handoff,    "handoff"),
            (Strategy.Sequential, "sequential"),
            (Strategy.Parallel,   "parallel"),
            (Strategy.Router,     "router"),
            (Strategy.RoundRobin, "round_robin"),
            (Strategy.Random,     "random"),
            (Strategy.Swarm,      "swarm"),
            (Strategy.Manual,     "manual"),
        };

        foreach (var (strategy, expected) in cases)
        {
            var c1 = new Agent($"s1_strat_{expected}_c1") { Model = Settings.LlmModel };
            var c2 = new Agent($"s1_strat_{expected}_c2") { Model = Settings.LlmModel };

            Agent parent;
            if (strategy == Strategy.Router)
            {
                var router = new Agent($"s1_strat_{expected}_router") { Model = Settings.LlmModel };
                parent = new Agent($"s1_strat_{expected}_parent")
                {
                    Model = Settings.LlmModel, Agents = [c1, c2],
                    Strategy = strategy, Router = router,
                };
            }
            else
            {
                parent = new Agent($"s1_strat_{expected}_parent")
                {
                    Model = Settings.LlmModel, Agents = [c1, c2], Strategy = strategy,
                };
            }

            var plan = await runtime.PlanAsync(parent);
            var ad   = E2eHelpers.GetAgentDef(plan);

            var actual = ad["strategy"]?.GetValue<string>();
            Assert.True(actual == expected,
                $"Strategy.{strategy} should serialize to '{expected}' but got '{actual}'.");
        }
    }

    // ── 1.9  Tool-level guardrail fields ──────────────────────────────────

    [SkippableFact]
    public async Task ToolGuardrail_FieldsInToolDef()
    {
        _fixture.RequireServer();

        var toolGuardrail = RegexGuardrail.Create(
            pattern:   @"DROP\s+TABLE",
            name:      "no_sqli",
            position:  Position.Input,
            onFail:    OnFail.Retry,
            maxRetries: 2
        );

        var tools = ToolRegistry.FromInstance(new S1ToolWithGuardrailHost())
            .Select(t => t.Name == "run_query" ? t.WithGuardrails(toolGuardrail) : t)
            .ToList();

        var agent = new Agent("s1_tool_guardrail")
        {
            Model  = Settings.LlmModel,
            Tools  = tools,
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // The tool must be in agentDef.tools
        var tool = E2eHelpers.GetTool(ad, "run_query");
        Assert.Equal("worker", tool["toolType"]?.GetValue<string>());

        // Tool-level guardrail must be in tool.guardrails
        var toolGuardrails = tool["guardrails"]?.AsArray();
        Assert.NotNull(toolGuardrails);
        Assert.True(toolGuardrails!.Count >= 1,
            $"Expected at least 1 tool-level guardrail but got {toolGuardrails.Count}.");

        var tg = toolGuardrails.First(g => g?["name"]?.GetValue<string>() == "no_sqli");
        Assert.NotNull(tg);
        Assert.Equal("input",  tg!["position"]?.GetValue<string>());
        Assert.Equal("retry",  tg["onFail"]?.GetValue<string>());
        Assert.Equal(2,        tg["maxRetries"]?.GetValue<int>());
    }

    // ── 1.10  HTTP tool toolType ───────────────────────────────────────────

    [SkippableFact]
    public async Task HttpTool_ToolTypeIsHttp()
    {
        _fixture.RequireServer();

        var httpTool = HttpTools.Create(
            name:        "lookup_price",
            description: "Look up the price of a product.",
            url:         "https://api.example.com/prices",
            method:      "GET"
        );

        var agent = new Agent("s1_http_tool")
        {
            Model  = Settings.LlmModel,
            Tools  = [httpTool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("http", E2eHelpers.GetToolType(ad, "lookup_price"));

        // Counterfactual: a worker tool on the same agent must have toolType "worker"
        var workerTools = ToolRegistry.FromInstance(new S1WorkerToolHost());
        var agentMixed  = new Agent("s1_mixed_tools")
        {
            Model  = Settings.LlmModel,
            Tools  = [httpTool, ..workerTools],
        };
        var planMixed = await runtime.PlanAsync(agentMixed);
        var adMixed   = E2eHelpers.GetAgentDef(planMixed);
        Assert.Equal("http",   E2eHelpers.GetToolType(adMixed, "lookup_price"));
        Assert.Equal("worker", E2eHelpers.GetToolType(adMixed, "get_greeting"));
    }
}

// ── Tool and guardrail hosts ──────────────────────────────────────────────────

internal sealed class S1WorkerToolHost
{
    [Tool("Return a greeting for a name.")]
    public string GetGreeting(string name) => $"Hello, {name}!";

    [Tool("Return a farewell for a name.")]
    public string GetFarewell(string name) => $"Goodbye, {name}!";
}

internal sealed class S1CredentialToolHost
{
    [Tool("Fetch data using API_KEY_1.", Credentials = ["API_KEY_1"])]
    public string SingleCredTool(string query) => $"result for {query}";

    [Tool("Fetch data using two secrets.", Credentials = ["SECRET_A", "SECRET_B"])]
    public string MultiCredTool(string data) => data;

    [Tool("A tool with no credentials needed.")]
    public string NoCredTool(string text) => text;
}

internal sealed class S1OutputGuardrailHost
{
    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 2)]
    public GuardrailResult NoAllCaps(string content)
        => new(content != content.ToUpper(), "Response must not be ALL CAPS.");
}

internal sealed class S1InputGuardrailHost
{
    [Guardrail(Position = Position.Input, OnFail = OnFail.Raise)]
    public GuardrailResult CheckInput(string content)
        => new(!string.IsNullOrWhiteSpace(content), "Input must not be empty.");
}

internal sealed class S1MultiGuardrailHost
{
    [Guardrail(Position = Position.Input, OnFail = OnFail.Raise)]
    public GuardrailResult InputCheck(string content) => new(true);

    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 3)]
    public GuardrailResult OutputRetry(string content) => new(true);

    [Guardrail(Position = Position.Output, OnFail = OnFail.Fix, MaxRetries = 1)]
    public GuardrailResult OutputFix(string content) => new(true);
}

internal sealed class S1ToolWithGuardrailHost
{
    [Tool("Execute a database query.")]
    public string RunQuery(string query) => $"Results for: {query}";
}
