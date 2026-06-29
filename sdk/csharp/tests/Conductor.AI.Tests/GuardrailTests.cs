// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// Fixes #3 (External guardrail), #5 (default on_fail = RAISE), #7 (human+input
/// validation throws).
/// </summary>
public class GuardrailTests
{
    // ── Fix #3: external guardrail ──────────────────────────────

    [Fact]
    public void External_has_no_handler_and_serializes_as_external()
    {
        var g = Guardrail.External("pii_remote");
        Assert.Equal("pii_remote", g.Name);
        Assert.Null(g.Handler);          // referenced-by-name, no local func
        Assert.True(g.External);

        var json = AgentConfigSerializer.SerializeGuardrail(g);
        Assert.Equal("external", json["guardrailType"]!.GetValue<string>());
        Assert.Equal("pii_remote", json["taskName"]!.GetValue<string>());
        Assert.Equal("pii_remote", json["name"]!.GetValue<string>());
    }

    [Fact]
    public void External_defaults_position_output_onfail_raise()
    {
        var g = Guardrail.External("x");
        Assert.Equal(Position.Output, g.Position);
        Assert.Equal(OnFail.Raise, g.OnFail);
    }

    // ── Fix #5: default on_fail = RAISE for regex + llm ─────────

    [Fact]
    public void Regex_default_onfail_is_raise()
    {
        var g = RegexGuardrail.Create("secret");
        Assert.Equal(OnFail.Raise, g.OnFail);
    }

    [Fact]
    public void Llm_default_onfail_is_raise()
    {
        var g = LLMGuardrail.Create("anthropic/claude-sonnet-4-6", "no bad stuff");
        Assert.Equal(OnFail.Raise, g.OnFail);
    }

    // ── Fix #7: human + input is invalid ────────────────────────

    [Fact]
    public void Human_onfail_with_input_position_throws_for_external()
    {
        Assert.Throws<ArgumentException>(() =>
            Guardrail.External("g", position: Position.Input, onFail: OnFail.Human));
    }

    [Fact]
    public void Human_onfail_with_input_position_throws_for_regex()
    {
        Assert.Throws<ArgumentException>(() =>
            RegexGuardrail.Create("x", position: Position.Input, onFail: OnFail.Human));
    }

    [Fact]
    public void Human_onfail_with_output_position_is_allowed()
    {
        var g = Guardrail.External("g", position: Position.Output, onFail: OnFail.Human);
        Assert.Equal(OnFail.Human, g.OnFail);
    }
}
