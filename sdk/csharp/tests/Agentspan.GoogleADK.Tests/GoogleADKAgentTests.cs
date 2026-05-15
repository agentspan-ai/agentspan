// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.GoogleADK;
using Xunit;

namespace Agentspan.GoogleADK.Tests;

/// <summary>
/// Plan-level (no LLM) tests for the Google ADK → Agentspan bridge. Mirrors
/// OpenAIAgentTests but asserts the ADK-specific wire shape: <c>instruction</c>
/// singular and <c>sub_agents</c> in raw config.
/// </summary>
public class GoogleADKAgentTests
{
    public sealed class TimeTools
    {
        [Tool("Today's date.")]
        public string Today() => "2026-01-01";
    }

    [Fact]
    public void Build_sets_framework_to_google_adk()
    {
        var agent = GoogleADKAgent.Builder().Name("a").Model("gemini-2.0-flash").Build();
        Assert.Equal("google_adk", agent.Framework);
    }

    [Fact]
    public void Tools_extracts_one_per_Tool_attribute_method()
    {
        var agent = GoogleADKAgent.Builder().Name("a").Model("m").Tools(new TimeTools()).Build();
        Assert.Single(agent.Tools);
    }

    [Fact]
    public void SubAgents_land_in_framework_config()
    {
        var sub = new Agent("sub") { Model = "gemini-2.0-flash", Instructions = "I am sub." };
        var agent = GoogleADKAgent.Builder()
            .Name("root")
            .Model("gemini-2.0-flash")
            .SubAgents(sub)
            .Build();

        Assert.NotNull(agent.FrameworkConfig);
        // COUNTERFACTUAL: if we used the OpenAI shape, the key would be "handoffs"
        // and the server's ADK normalizer would drop the sub-agent.
        Assert.True(agent.FrameworkConfig!.ContainsKey("sub_agents"));
        Assert.False(agent.FrameworkConfig.ContainsKey("handoffs"));
    }

    [Fact]
    public void Serializer_emits_instruction_singular_for_adk()
    {
        var agent = GoogleADKAgent.Builder().Name("a").Model("m").Instruction("hello").Build();
        var json  = SerializeAgentForTest(agent);

        // COUNTERFACTUAL: if the serializer kept the OpenAI plural "instructions"
        // key, the ADK server normalizer never picks up the system prompt.
        Assert.Equal("hello", json["instruction"]?.GetValue<string>());
        Assert.Null(json["instructions"]);
    }

    [Fact]
    public void Serializer_emits_worker_ref_tool_shape()
    {
        var agent = GoogleADKAgent.Builder().Name("a").Model("m").Tools(new TimeTools()).Build();
        var json  = SerializeAgentForTest(agent);
        var tools = json["tools"] as JsonArray;

        Assert.NotNull(tools);
        Assert.NotNull(tools![0]?["_worker_ref"]);
    }

    private static JsonObject SerializeAgentForTest(Agent agent)
    {
        var t  = typeof(Agent).Assembly.GetType("Agentspan.AgentConfigSerializer", throwOnError: true)!;
        var mi = t.GetMethod("SerializeAgent", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        return (JsonObject)mi.Invoke(null, new object[] { agent })!;
    }
}
