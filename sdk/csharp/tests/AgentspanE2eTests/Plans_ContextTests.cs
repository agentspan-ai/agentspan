// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Context + planner_context tests — mirror Python's test_planner_context.py,
// TS's planner-context.test.ts, and Java's ContextTest. The four SDKs MUST
// emit identical wire payloads; this file pins the C# side.
//
// CLAUDE.md rule: no LLM for validation. Pure dataclass + serializer.

using System.Collections.Generic;
using System.Text.Json.Nodes;
using Xunit;
using Agentspan;
using Agentspan.Plans;

namespace Agentspan.E2eTests;

public sealed class Plans_ContextTests
{
    // ── Context dataclass ──────────────────────────────────

    [Fact]
    public void TextShorthandConstruction()
    {
        var c = Context.FromText("rule one");
        Assert.Equal("rule one", c.Text);
        Assert.Null(c.Url);
    }

    [Fact]
    public void UrlShorthandHasDefaults()
    {
        var c = Context.FromUrl("https://x/y");
        Assert.Equal("https://x/y", c.Url);
        Assert.Null(c.Text);
        Assert.True(c.Required);
        Assert.Equal(16384, c.MaxBytes);
    }

    [Fact]
    public void ToJsonTextOnlyIsMinimal()
    {
        // Text-only entries serialise as a single-key object — no url,
        // headers, required, maxBytes. Keeps the wire payload tight.
        var json = Context.FromText("rule").ToJson();
        Assert.Equal("rule", (string?)json["text"]);
        Assert.False(json.ContainsKey("url"));
        Assert.False(json.ContainsKey("headers"));
        Assert.False(json.ContainsKey("required"));
        Assert.False(json.ContainsKey("maxBytes"));
    }

    [Fact]
    public void ToJsonUrlOnlyWithDefaultsIsMinimal()
    {
        // URL with all defaults: only url on the wire (server applies the
        // same defaults). Mirrors Python/TS/Java behaviour.
        var json = Context.FromUrl("https://x/").ToJson();
        Assert.Equal("https://x/", (string?)json["url"]);
        Assert.False(json.ContainsKey("required"));
        Assert.False(json.ContainsKey("maxBytes"));
    }

    [Fact]
    public void ToJsonUrlFullOptionsPreservesCredentialPlaceholder()
    {
        // Credential placeholder MUST pass through verbatim — the
        // ${} -> #{} escape is the server's job. The SDK must NOT
        // pre-escape; otherwise the credential resolver wouldn't see
        // #{NAME} on the wire and resolution would silently no-op.
        var c = Context.FromUrl(
            "https://confluence.example.com/page",
            headers: new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer ${CONFLUENCE_TOKEN}",
            },
            required: false,
            maxBytes: 8192);
        var json = c.ToJson();
        Assert.Equal("https://confluence.example.com/page", (string?)json["url"]);
        var headers = json["headers"]!.AsObject();
        Assert.Equal("Bearer ${CONFLUENCE_TOKEN}", (string?)headers["Authorization"]);
        Assert.False((bool)json["required"]!);
        Assert.Equal(8192, (int)json["maxBytes"]!);
    }

    // ── Agent + AgentConfigSerializer wiring ───────────────

    [Fact]
    public void SerializerEmitsPlannerContextWithMixedEntries()
    {
        var planner = AgentBuilder.Create("planner_sub").WithModel("openai/gpt-4o-mini").Build();
        var stub = new ToolDef
        {
            Name = "stub",
            Description = "stub",
            InputSchema = new JsonObject
            {
                ["type"] = "object",
                ["properties"] = new JsonObject(),
            },
        };
        var harness = AgentBuilder.Create("h")
            .WithModel("openai/gpt-4o-mini")
            .WithStrategy(Strategy.PlanExecute)
            .WithPlanner(planner)
            .WithTools(stub)
            .WithPlannerContext(
                Context.FromText("inline rule"),
                Context.FromUrl(
                    "https://confluence.example.com/onboarding",
                    headers: new Dictionary<string, string>
                    {
                        ["Authorization"] = "Bearer ${CONFLUENCE_TOKEN}",
                    },
                    required: false,
                    maxBytes: 8192))
            .Build();

        var cfg = SerializeAgentConfigForTest(harness);
        var ctx = cfg["plannerContext"]!.AsArray();
        Assert.Equal(2, ctx.Count);
        Assert.Equal("inline rule", (string?)ctx[0]!["text"]);
        Assert.Equal(
            "https://confluence.example.com/onboarding",
            (string?)ctx[1]!["url"]);
        Assert.Equal(
            "Bearer ${CONFLUENCE_TOKEN}",
            (string?)ctx[1]!["headers"]!["Authorization"]);
        Assert.False((bool)ctx[1]!["required"]!);
        Assert.Equal(8192, (int)ctx[1]!["maxBytes"]!);
    }

    [Fact]
    public void SerializerOmitsPlannerContextWhenUnset()
    {
        // Counterfactual: without PlannerContext the wire field MUST NOT
        // appear. Pairs with the positive test — without this, the
        // positive case could vacuously pass if the serializer always
        // emitted the field.
        var planner = AgentBuilder.Create("planner_sub").WithModel("openai/gpt-4o-mini").Build();
        var stub = new ToolDef
        {
            Name = "stub",
            Description = "stub",
            InputSchema = new JsonObject
            {
                ["type"] = "object",
                ["properties"] = new JsonObject(),
            },
        };
        var harness = AgentBuilder.Create("h")
            .WithModel("openai/gpt-4o-mini")
            .WithStrategy(Strategy.PlanExecute)
            .WithPlanner(planner)
            .WithTools(stub)
            .Build();

        var cfg = SerializeAgentConfigForTest(harness);
        Assert.False(cfg.ContainsKey("plannerContext"));
    }

    [Fact]
    public void SerializerThrowsOnPlannerContextWithNonPlanExecuteStrategy()
    {
        // Same guard shape as Python/TS/Java — setting PlannerContext on
        // anything other than Strategy.PlanExecute is a silent bug.
        // Serializer is the last line of defence.
        var sub = AgentBuilder.Create("sub").WithModel("openai/gpt-4o-mini").Build();
        var harness = AgentBuilder.Create("h")
            .WithModel("openai/gpt-4o-mini")
            .WithStrategy(Strategy.Handoff)
            .WithAgents(sub)
            .WithPlannerContext("rule")
            .Build();

        var ex = Assert.Throws<System.InvalidOperationException>(
            () => SerializeAgentConfigForTest(harness));
        Assert.Contains("PlanExecute", ex.Message);
    }

    /// <summary>
    /// AgentConfigSerializer is `internal static` (the public entry point
    /// is Serialize which wraps the agent config in the POST /agent/start
    /// envelope). The test assembly can't reference the type name directly
    /// — look it up by string via Assembly.GetType, matching the pattern
    /// OpenAIAgentTests already uses.
    /// </summary>
    private static JsonObject SerializeAgentConfigForTest(Agent agent)
    {
        var t = typeof(Agent).Assembly
            .GetType("Agentspan.AgentConfigSerializer", throwOnError: true)!;
        var mi = t.GetMethod(
            "SerializeAgent",
            System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        try
        {
            return (JsonObject)mi.Invoke(null, new object[] { agent })!;
        }
        catch (System.Reflection.TargetInvocationException tie)
            when (tie.InnerException is not null)
        {
            // Unwrap so Assert.Throws<InvalidOperationException> sees the
            // real exception, not the reflection wrapper.
            throw tie.InnerException;
        }
    }
}
