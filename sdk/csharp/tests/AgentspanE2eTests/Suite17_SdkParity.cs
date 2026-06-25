// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 17 — SDK parity features: handoff triggers, text gate, dynamic
// instructions, lifecycle callbacks (agent/tool + composable handlers),
// agent-from-method ([AgentDef] + FromInstance), and worker-tuning env vars.
//
// Validation is DETERMINISTIC: plan() agentDef structure, in-process object
// graph, and tool side-effect counters. No LLM judges output text.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.Json;
using System.Threading;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite17_SdkParity
{
    private readonly E2eFixture _fixture;
    public Suite17_SdkParity(E2eFixture fixture) => _fixture = fixture;

    // ── 17.1  Handoff triggers serialize into agentDef.handoffs ──────────

    [SkippableFact]
    public async Task Handoffs_SerializeWithTypeAndFields()
    {
        _fixture.RequireServer();

        var billing = new Agent("s17_billing") { Model = Settings.LlmModel, Instructions = "Handle billing." };
        var refund  = new Agent("s17_refund")  { Model = Settings.LlmModel, Instructions = "Handle refunds." };

        var swarm = new Agent("s17_swarm")
        {
            Model        = Settings.LlmModel,
            Instructions = "Route the customer.",
            Strategy     = Strategy.Swarm,
            Agents       = [billing, refund],
            Handoffs =
            [
                OnTextMention.Of("refund", "s17_refund"),
                OnToolResult.Of("check_eligibility", "s17_billing", "eligible"),
                new OnCondition("s17_refund", ctx => ctx.TryGetValue("result", out var r) && (r?.ToString()?.Length ?? 0) > 9999),
            ],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(swarm);
        var agentDef = E2eHelpers.GetAgentDef(plan);

        var handoffs = agentDef["handoffs"]?.AsArray();
        Assert.NotNull(handoffs);
        Assert.Equal(3, handoffs!.Count);

        var byType = handoffs
            .Where(h => h is not null)
            .ToDictionary(h => h!["type"]!.GetValue<string>(), h => h!);

        Assert.Equal("s17_refund", byType["on_text_mention"]["target"]!.GetValue<string>());
        Assert.Equal("refund",     byType["on_text_mention"]["text"]!.GetValue<string>());

        Assert.Equal("check_eligibility", byType["on_tool_result"]["toolName"]!.GetValue<string>());
        Assert.Equal("eligible",          byType["on_tool_result"]["resultContains"]!.GetValue<string>());

        Assert.Equal("s17_swarm_handoff_s17_refund", byType["on_condition"]["taskName"]!.GetValue<string>());

        // Counterfactual: an agent without handoffs has none.
        var plain = await runtime.PlanAsync(new Agent("s17_no_handoff") { Model = Settings.LlmModel });
        var plainHandoffs = E2eHelpers.GetAgentDef(plain)["handoffs"]?.AsArray();
        Assert.True(plainHandoffs is null || plainHandoffs.Count == 0,
            "Agent without handoffs must not emit a handoffs array.");
    }

    // ── 17.2  OnCondition predicate logic (in-process, deterministic) ────

    [Fact]
    public void OnCondition_PredicateAndTextMentionEvaluate()
    {
        var ctxLong  = new Dictionary<string, object?> { ["result"] = new string('x', 10), ["tool_name"] = "", ["tool_result"] = "" };
        var ctxShort = new Dictionary<string, object?> { ["result"] = "hi", ["tool_name"] = "", ["tool_result"] = "" };

        var cond = new OnCondition("t", c => (c["result"]?.ToString()?.Length ?? 0) > 5);
        Assert.True(cond.ShouldHandoff(ctxLong));
        Assert.False(cond.ShouldHandoff(ctxShort));

        var mention = OnTextMention.Of("refund", "t");
        Assert.True(mention.ShouldHandoff(new Dictionary<string, object?> { ["result"] = "please refund me" }));
        Assert.False(mention.ShouldHandoff(new Dictionary<string, object?> { ["result"] = "all good" }));

        var tool = OnToolResult.Of("check", "t", "ok");
        Assert.True(tool.ShouldHandoff(new Dictionary<string, object?> { ["tool_name"] = "check", ["tool_result"] = "status: ok" }));
        Assert.False(tool.ShouldHandoff(new Dictionary<string, object?> { ["tool_name"] = "check", ["tool_result"] = "status: no" }));
        Assert.False(tool.ShouldHandoff(new Dictionary<string, object?> { ["tool_name"] = "other", ["tool_result"] = "ok" }));
    }

    // ── 17.3  TextGate serializes into a sequential pipeline ─────────────

    [SkippableFact]
    public async Task TextGate_SerializesOnPipelineStage()
    {
        _fixture.RequireServer();

        var checker = new Agent("s17_checker") { Model = Settings.LlmModel, Instructions = "Say OK or STOP.", Gate = new TextGate("STOP", caseSensitive: false) };
        var fixer   = new Agent("s17_fixer")   { Model = Settings.LlmModel, Instructions = "Fix it." };
        var pipeline = checker >> fixer;

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(pipeline);
        var agentDef = E2eHelpers.GetAgentDef(plan);

        // The gate lives on the first sub-agent (checker).
        var stage0 = agentDef["agents"]?.AsArray()?.FirstOrDefault(a => a?["name"]?.GetValue<string>() == "s17_checker");
        Assert.NotNull(stage0);
        var gate = stage0!["gate"];
        Assert.NotNull(gate);
        Assert.Equal("text_contains", gate!["type"]!.GetValue<string>());
        Assert.Equal("STOP",          gate["text"]!.GetValue<string>());
        Assert.False(gate["caseSensitive"]!.GetValue<bool>());
    }

    // ── 17.4  Dynamic (callable) instructions resolve at serialize time ──

    [SkippableFact]
    public async Task DynamicInstructions_ResolveFreshEachSerialization()
    {
        _fixture.RequireServer();

        var counter = 0;
        var agent = new Agent("s17_dynamic") { Model = Settings.LlmModel, InstructionsFn = () => $"Run number {Interlocked.Increment(ref counter)}." };

        await using var runtime = new AgentRuntime();
        var p1 = E2eHelpers.GetAgentDef(await runtime.PlanAsync(agent));
        var p2 = E2eHelpers.GetAgentDef(await runtime.PlanAsync(agent));

        var i1 = p1["instructions"]!.GetValue<string>();
        var i2 = p2["instructions"]!.GetValue<string>();

        Assert.Equal("Run number 1.", i1);
        Assert.Equal("Run number 2.", i2);
        Assert.NotEqual(i1, i2);  // counterfactual: a static string would be identical
    }

    // ── 17.5  Lifecycle callbacks (agent/tool + composable handler) ──────

    [SkippableFact]
    public async Task Callbacks_AgentToolAndHandlerPositionsSerialize()
    {
        _fixture.RequireServer();

        var agent = new Agent("s17_callbacks")
        {
            Model               = Settings.LlmModel,
            Instructions        = "Answer.",
            Tools               = ToolRegistry.FromInstance(new S17PingTool()),
            BeforeAgentCallback = _ => null,
            AfterToolCallback   = _ => null,
            Callbacks           = [new S17ToolStartHandler()],  // overrides OnToolStart → before_tool
        };

        await using var runtime = new AgentRuntime();
        var agentDef = E2eHelpers.GetAgentDef(await runtime.PlanAsync(agent));

        var positions = agentDef["callbacks"]?.AsArray()
            .Select(c => c?["position"]?.GetValue<string>())
            .Where(p => p is not null)
            .ToHashSet();

        Assert.NotNull(positions);
        Assert.Contains("before_agent", positions!);
        Assert.Contains("after_tool",   positions!);
        Assert.Contains("before_tool",  positions!);  // contributed by the CallbackHandler

        // Counterfactual: each position appears exactly once even though before_tool
        // could come from both a func and a handler.
        var beforeToolCount = agentDef["callbacks"]!.AsArray()
            .Count(c => c?["position"]?.GetValue<string>() == "before_tool");
        Assert.Equal(1, beforeToolCount);
    }

    // ── 17.6  Agent-from-method: [AgentDef] + FromInstance ───────────────

    [Fact]
    public void FromInstance_BuildsAgentsToolsAndSubAgents()
    {
        var host = new S17AgentHost();

        var agents = Agent.FromInstance(host);
        var byName = agents.ToDictionary(a => a.Name);

        Assert.Contains("greeter", byName.Keys);
        Assert.Contains("coordinator", byName.Keys);

        // greeter has the [Tool] method attached (default tools = "*").
        Assert.Contains(byName["greeter"].Tools, t => t.Name == "say_hi");

        // coordinator wires greeter as a sub-agent under the declared strategy.
        var coordinator = byName["coordinator"];
        Assert.Equal(Strategy.Sequential, coordinator.Strategy);
        Assert.Contains(coordinator.Agents, a => a.Name == "greeter");

        // Single-agent resolution by name works too.
        var single = Agent.FromInstance(host, "greeter");
        Assert.Equal("greeter", single.Name);

        // Dynamic-instruction method (returns string) became InstructionsFn.
        Assert.NotNull(byName["greeter"].InstructionsFn);
        Assert.Equal("Be friendly.", byName["greeter"].InstructionsFn!());
    }

    [SkippableFact]
    public async Task FromInstance_AgentRunsAndToolFires()
    {
        _fixture.RequireServer();

        var host  = new S17AgentHost();
        var agent = Agent.FromInstance(host, "greeter");
        agent.Model = Settings.LlmModel;  // [AgentDef] left model unset; supply for the run

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Greet the user by calling say_hi.");

        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
        Assert.True(host.SayHiCalls > 0,
            $"COUNTERFACTUAL: if [AgentDef] tool attachment broke, say_hi never runs. Calls={host.SayHiCalls}.");
    }

    // ── 17.7  Worker-tuning env vars are read by the runtime ─────────────

    [Fact]
    public void WorkerTuning_ReadsEnvVars()
    {
        var prevThreads = Environment.GetEnvironmentVariable("AGENTSPAN_WORKER_THREADS");
        var prevPoll    = Environment.GetEnvironmentVariable("AGENTSPAN_WORKER_POLL_INTERVAL");
        try
        {
            Environment.SetEnvironmentVariable("AGENTSPAN_WORKER_THREADS", "4");
            Environment.SetEnvironmentVariable("AGENTSPAN_WORKER_POLL_INTERVAL", "250");

            using var runtime = new AgentRuntime();
            Assert.Equal(4,   runtime.WorkerThreadCount);
            Assert.Equal(250, runtime.WorkerPollIntervalMs);
        }
        finally
        {
            Environment.SetEnvironmentVariable("AGENTSPAN_WORKER_THREADS", prevThreads);
            Environment.SetEnvironmentVariable("AGENTSPAN_WORKER_POLL_INTERVAL", prevPoll);
        }

        // Counterfactual: unset → defaults.
        Environment.SetEnvironmentVariable("AGENTSPAN_WORKER_THREADS", null);
        Environment.SetEnvironmentVariable("AGENTSPAN_WORKER_POLL_INTERVAL", null);
        using var def = new AgentRuntime();
        Assert.Equal(1,   def.WorkerThreadCount);
        Assert.Equal(100, def.WorkerPollIntervalMs);
    }
}

// ── Tool / agent hosts ──────────────────────────────────────────────────────

internal sealed class S17PingTool
{
    [Tool("Ping — forces DO_WHILE compilation so callback workers dispatch.")]
    public Dictionary<string, object> Ping() => new() { ["pong"] = true };
}

internal sealed class S17ToolStartHandler : CallbackHandler
{
    public int Count;
    public override Dictionary<string, object>? OnToolStart(Dictionary<string, JsonElement> kwargs)
    {
        Interlocked.Increment(ref Count);
        return null;  // observe only
    }
}

internal sealed class S17AgentHost
{
    private int _sayHiCalls;
    public int SayHiCalls => _sayHiCalls;

    [Tool("Greet the user.")]
    public Dictionary<string, object> SayHi()
    {
        Interlocked.Increment(ref _sayHiCalls);
        return new() { ["greeting"] = "s17_hello" };
    }

    // Dynamic instructions: a no-arg string method becomes InstructionsFn.
    [AgentDef(Name = "greeter", Tools = new[] { "say_hi" })]
    public string Greeter() => "Be friendly.";

    // void method: defined entirely by the attribute; wires greeter as a sub-agent.
    [AgentDef(Name = "coordinator", Tools = new string[0], Agents = new[] { "greeter" }, Strategy = Strategy.Sequential)]
    public void Coordinator() { }
}
