// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.OpenAI;
using Xunit;

namespace Agentspan.OpenAI.Tests;

/// <summary>
/// Plan-level (no LLM) tests for the OpenAI Agents SDK → Agentspan bridge.
/// Each test asserts a specific wire-shape property and is designed to fail
/// if the bridge silently drops or mangles that property.
/// </summary>
public class OpenAIAgentTests
{
    public sealed class CalcTools
    {
        [Tool("Add two ints.")]
        public int Add(int a, int b) => a + b;

        [Tool("Multiply two ints.")]
        public int Multiply(int a, int b) => a * b;

        // No [Tool] — should be ignored.
        public int Unannotated(int a) => a + 1;
    }

    [Fact]
    public void Build_sets_framework_to_openai()
    {
        var agent = OpenAIAgent.Builder().Name("a").Model("openai/gpt-4o-mini").Build();
        // COUNTERFACTUAL: if Builder drops the framework tag, this is null.
        Assert.Equal("openai", agent.Framework);
    }

    [Fact]
    public void Tools_extracts_one_per_Tool_attribute_method()
    {
        var agent = OpenAIAgent.Builder().Name("a").Model("m").Tools(new CalcTools()).Build();
        // COUNTERFACTUAL: count would be 3 if non-attributed methods leak in, 0 if all dropped.
        Assert.Equal(2, agent.Tools.Count);
    }

    [Fact]
    public void Handoffs_land_in_framework_config()
    {
        var sub = new Agent("sub") { Model = "openai/gpt-4o-mini", Instructions = "I am sub." };
        var agent = OpenAIAgent.Builder()
            .Name("root")
            .Model("openai/gpt-4o-mini")
            .Handoffs(sub)
            .Build();

        // COUNTERFACTUAL: if Handoffs aren't propagated, FrameworkConfig is null
        // or the "handoffs" key is missing.
        Assert.NotNull(agent.FrameworkConfig);
        Assert.True(agent.FrameworkConfig!.ContainsKey("handoffs"));
    }

    [Fact]
    public void Build_throws_when_name_missing()
    {
        // COUNTERFACTUAL: without the validation guard, this returns an Agent
        // with an empty name (which would fail downstream with a confusing error).
        Assert.Throws<ArgumentException>(() => OpenAIAgent.Builder().Model("m").Build());
    }

    [Fact]
    public void Serializer_emits_instructions_plural_for_openai()
    {
        var agent = OpenAIAgent.Builder().Name("a").Model("m").Instructions("hello").Build();
        var json = SerializeAgentForTest(agent);

        // COUNTERFACTUAL: if the serializer used the ADK ("instruction" singular)
        // for OpenAI, the LLM would not see the system prompt.
        Assert.Equal("hello", json["instructions"]?.GetValue<string>());
        Assert.Null(json["instruction"]);
    }

    [Fact]
    public void Serializer_emits_worker_ref_tool_shape()
    {
        var agent = OpenAIAgent.Builder().Name("a").Model("m").Tools(new CalcTools()).Build();
        var json  = SerializeAgentForTest(agent);
        var tools = json["tools"] as JsonArray;

        Assert.NotNull(tools);
        // COUNTERFACTUAL: if the serializer used the default `{name, inputSchema}`
        // shape, the OpenAINormalizer drops the tool and the LLM sees no params.
        Assert.NotNull(tools![0]?["_worker_ref"]);
        Assert.NotNull(tools[0]?["parameters"]);
    }

    // Reflect into the internal serializer; framework tests don't have InternalsVisibleTo,
    // so we go through the public AgentRuntime path that calls it via the wire.
    private static JsonObject SerializeAgentForTest(Agent agent)
    {
        var t  = typeof(Agent).Assembly.GetType("Agentspan.AgentConfigSerializer", throwOnError: true)!;
        var mi = t.GetMethod("SerializeAgent", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        return (JsonObject)mi.Invoke(null, new object[] { agent })!;
    }
}
