// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Text.Json.Nodes;
using Conductor.AI;
using Xunit;

namespace Conductor.AI.Tests;

/// <summary>
/// SET 1 — wire parity for six AgentConfig fields the C# serializer previously
/// omitted: synthesize, prefillTools, cliConfig, reasoningEffort,
/// contextWindowBudget, maskedFields. Exact keys/shapes mirror Python's
/// config_serializer.py and Java's AgentConfigSerializer.java.
/// </summary>
public class AgentConfigFieldsTests
{
    private static JsonObject SerializeAgent(Agent agent) =>
        AgentConfigSerializer.SerializeAgent(agent);

    // ── synthesize (bool) — only emitted when explicitly disabled ──────

    [Fact]
    public void Synthesize_default_true_emits_nothing()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["synthesize"]);
    }

    [Fact]
    public void Synthesize_false_emits_false()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o", Synthesize = false };
        var cfg = SerializeAgent(agent);
        Assert.False(cfg["synthesize"]!.GetValue<bool>());
    }

    // ── prefillTools — [{toolName, arguments}] ─────────────────────────

    [Fact]
    public void PrefillTools_emits_toolName_and_arguments()
    {
        var agent = new Agent("a")
        {
            Model = "openai/gpt-4o",
            PrefillTools =
            [
                new PrefillToolCall("fetch_user",
                    new Dictionary<string, object> { ["id"] = 42 }),
            ],
        };

        var cfg = SerializeAgent(agent);
        var arr = cfg["prefillTools"]!.AsArray();
        Assert.Single(arr);
        var pt = arr[0]!.AsObject();
        Assert.Equal("fetch_user", pt["toolName"]!.GetValue<string>());
        Assert.Equal(42, pt["arguments"]!.AsObject()["id"]!.GetValue<int>());
    }

    [Fact]
    public void PrefillTools_unset_emits_nothing()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["prefillTools"]);
    }

    // ── cliConfig — {enabled, allowedCommands, timeout, allowShell, workingDir?} ──

    [Fact]
    public void CliConfig_emits_full_shape()
    {
        var agent = new Agent("ops")
        {
            Model = "openai/gpt-4o",
            CliConfig = new CliConfig(
                Enabled: true,
                AllowedCommands: ["git", "gh"],
                Timeout: 60,
                AllowShell: true,
                WorkingDir: "/repo"),
        };

        var cfg = SerializeAgent(agent);
        var cli = cfg["cliConfig"]!.AsObject();
        Assert.True(cli["enabled"]!.GetValue<bool>());
        Assert.Equal(new[] { "git", "gh" },
            cli["allowedCommands"]!.AsArray().Select(n => n!.GetValue<string>()));
        Assert.Equal(60, cli["timeout"]!.GetValue<int>());
        Assert.True(cli["allowShell"]!.GetValue<bool>());
        Assert.Equal("/repo", cli["workingDir"]!.GetValue<string>());
    }

    [Fact]
    public void CliConfig_omits_workingDir_when_null()
    {
        var agent = new Agent("ops")
        {
            Model = "openai/gpt-4o",
            CliConfig = new CliConfig(AllowedCommands: ["git"]),
        };
        var cfg = SerializeAgent(agent);
        var cli = cfg["cliConfig"]!.AsObject();
        Assert.False(cli.ContainsKey("workingDir"));
        // Defaults: enabled true, timeout 30, allowShell false
        Assert.True(cli["enabled"]!.GetValue<bool>());
        Assert.Equal(30, cli["timeout"]!.GetValue<int>());
        Assert.False(cli["allowShell"]!.GetValue<bool>());
    }

    [Fact]
    public void CliConfig_unset_emits_nothing()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["cliConfig"]);
    }

    // ── reasoningEffort (string) ───────────────────────────────────────

    [Fact]
    public void ReasoningEffort_emits_string()
    {
        var agent = new Agent("a") { Model = "openai/o3", ReasoningEffort = "high" };
        var cfg = SerializeAgent(agent);
        Assert.Equal("high", cfg["reasoningEffort"]!.GetValue<string>());
    }

    [Fact]
    public void ReasoningEffort_unset_emits_nothing()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["reasoningEffort"]);
    }

    // ── contextWindowBudget (int) ──────────────────────────────────────

    [Fact]
    public void ContextWindowBudget_emits_int()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o", ContextWindowBudget = 120000 };
        var cfg = SerializeAgent(agent);
        Assert.Equal(120000, cfg["contextWindowBudget"]!.GetValue<int>());
    }

    [Fact]
    public void ContextWindowBudget_unset_emits_nothing()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["contextWindowBudget"]);
    }

    // ── maskedFields (list of strings) ─────────────────────────────────

    [Fact]
    public void MaskedFields_emits_string_list()
    {
        var agent = new Agent("a")
        {
            Model = "openai/gpt-4o",
            MaskedFields = ["ssn", "password"],
        };
        var cfg = SerializeAgent(agent);
        Assert.Equal(new[] { "ssn", "password" },
            cfg["maskedFields"]!.AsArray().Select(n => n!.GetValue<string>()));
    }

    [Fact]
    public void MaskedFields_unset_emits_nothing()
    {
        var agent = new Agent("a") { Model = "openai/gpt-4o" };
        var cfg = SerializeAgent(agent);
        Assert.Null(cfg["maskedFields"]);
    }
}
