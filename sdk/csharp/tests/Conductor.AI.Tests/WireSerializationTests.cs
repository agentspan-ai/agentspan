// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;
using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// Wire-serialization parity tests: assert the C# serializer emits the same
/// shapes as Python/Java/TS and what the server contract reads.
///
/// 1. thinkingBudgetTokens → nested thinkingConfig {enabled, budgetTokens}
/// 2. promptTemplate → nested under instructions {type: prompt_template, ...}
/// 3. maxTurns defaults to 25 and is always emitted
/// </summary>
public class WireSerializationTests
{
    private static JsonObject SerializeAgent(Agent agent) =>
        AgentConfigSerializer.SerializeAgent(agent);

    // ── Fix #1: thinking budget nests under thinkingConfig ──────────

    [Fact]
    public void ThinkingBudget_emits_nested_thinkingConfig()
    {
        var agent = new Agent("thinker") { Model = "anthropic/claude", ThinkingBudgetTokens = 4096 };

        var cfg = SerializeAgent(agent);

        // No flat key
        Assert.Null(cfg["thinkingBudgetTokens"]);

        // Nested object {enabled: true, budgetTokens: 4096}
        var tc = cfg["thinkingConfig"]!.AsObject();
        Assert.True(tc["enabled"]!.GetValue<bool>());
        Assert.Equal(4096, tc["budgetTokens"]!.GetValue<int>());
    }

    [Fact]
    public void ThinkingBudget_unset_emits_nothing()
    {
        var agent = new Agent("plain") { Model = "anthropic/claude" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["thinkingConfig"]);
        Assert.Null(cfg["thinkingBudgetTokens"]);
    }

    // ── Fix #2: prompt template nests under instructions ────────────

    [Fact]
    public void PromptTemplate_nests_under_instructions()
    {
        var agent = new Agent("templated")
        {
            Model = "anthropic/claude",
            PromptTemplateInstructions = new PromptTemplate(
                "greet",
                new Dictionary<string, string> { ["tone"] = "warm" },
                Version: 3),
        };

        var cfg = SerializeAgent(agent);

        // No top-level promptTemplate key
        Assert.Null(cfg["promptTemplate"]);

        var instr = cfg["instructions"]!.AsObject();
        Assert.Equal("prompt_template", instr["type"]!.GetValue<string>());
        Assert.Equal("greet", instr["name"]!.GetValue<string>());
        Assert.Equal(3, instr["version"]!.GetValue<int>());
        Assert.Equal("warm", instr["variables"]!.AsObject()["tone"]!.GetValue<string>());
    }

    [Fact]
    public void PromptTemplate_without_variables_or_version_minimal()
    {
        var agent = new Agent("templated")
        {
            Model = "anthropic/claude",
            PromptTemplateInstructions = new PromptTemplate("greet"),
        };

        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["promptTemplate"]);

        var instr = cfg["instructions"]!.AsObject();
        Assert.Equal("prompt_template", instr["type"]!.GetValue<string>());
        Assert.Equal("greet", instr["name"]!.GetValue<string>());
        Assert.Null(instr["version"]);
        Assert.Null(instr["variables"]);
    }

    // ── Fix #3: maxTurns defaults to 25 and always emitted ──────────

    [Fact]
    public void MaxTurns_defaults_to_25_and_is_emitted()
    {
        var agent = new Agent("default") { Model = "anthropic/claude" };

        Assert.Equal(25, agent.MaxTurns);

        var cfg = SerializeAgent(agent);
        Assert.NotNull(cfg["maxTurns"]);
        Assert.Equal(25, cfg["maxTurns"]!.GetValue<int>());
    }

    [Fact]
    public void MaxTurns_explicit_value_is_emitted()
    {
        var agent = new Agent("custom") { Model = "anthropic/claude", MaxTurns = 7 };
        var cfg = SerializeAgent(agent);
        Assert.Equal(7, cfg["maxTurns"]!.GetValue<int>());
    }
}
