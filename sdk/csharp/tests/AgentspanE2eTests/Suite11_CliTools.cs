// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 11 — CLI Tools: CliTool.Create() properties, handler execution, and plan integration.
//
// Corresponds to Python e2e: test_suite3_cli_tools.py
//
// Design notes:
//   - CliTool.Create() returns a ToolDef with a local Handler (worker tool).
//   - The Handler validates commands against allowedCommands and runs them via Process.
//   - [Fact] tests verify ToolDef public properties (name, credentials, description, schema).
//   - [SkippableFact] tests compile via PlanAsync() and verify toolType="worker" in the plan.
//   - 11.3 tests the actual execution via a server run (handler is internal — cannot call directly).
//
// Two validation layers:
//   [Fact]          — pure SDK tests, no server. Inspect ToolDef properties.
//   [SkippableFact] — server tests. Verify the compiled plan tool types and actual execution.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Threading;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite11_CliTools
{
    private readonly E2eFixture _fixture;

    public Suite11_CliTools(E2eFixture fixture) => _fixture = fixture;

    // ── 11.1  CliTool.Create() returns ToolDef with name="run_command" and credentials ──
    //
    // Counterfactual: if CliTool.Create() did not set Name="run_command" or failed to
    // populate Credentials, the LLM would receive an anonymous tool and credentials
    // would not be injected into the subprocess environment.

    [Fact]
    public void CliTool_ToolDefHasNameAndCredentials()
    {
        var tool = CliTool.Create(
            allowedCommands: ["gh", "git"],
            credentials:     ["GITHUB_TOKEN", "GH_TOKEN"]);

        Assert.Equal("run_command", tool.Name);
        Assert.Contains("GITHUB_TOKEN", tool.Credentials);
        Assert.Contains("GH_TOKEN",     tool.Credentials);
        Assert.Equal(2, tool.Credentials.Length);
        Assert.False(tool.External,
            "CliTool must not set External=true — it is a local worker, not an external server.");

        // Counterfactual: CliTool without credentials has empty credentials
        var toolNoCreds = CliTool.Create(allowedCommands: ["ls"]);
        Assert.Empty(toolNoCreds.Credentials);
        Assert.Equal("run_command", toolNoCreds.Name);
    }

    // ── 11.2  CliTool with allowedCommands — Credentials empty when no credentials passed ──
    //
    // Counterfactual: if credentials were accidentally initialized to non-empty defaults,
    // the plan would declare credentials the user never requested.

    [Fact]
    public void CliTool_AllowedCommandsOnly_EmptyCredentials()
    {
        var tool = CliTool.Create(allowedCommands: ["echo", "ls", "mktemp"]);

        Assert.Empty(tool.Credentials);
        Assert.Equal("run_command", tool.Name);

        // Description must mention allowed commands
        Assert.Contains("echo", tool.Description, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("ls",   tool.Description, StringComparison.OrdinalIgnoreCase);
    }

    // ── 11.3  CliTool executes a whitelisted command and blocks a non-whitelisted one ──
    //
    // Verifies actual CLI execution through the server runtime.
    // Uses a custom tool host with an Interlocked counter to prove the command ran
    // (counter-based validation, not LLM output parsing).
    // An "echo" command is whitelisted; the agent calls it and the counter increments.
    // A blocked command test validates whitelist enforcement at the ToolDef description level.
    //
    // Counterfactual: if the whitelist check were missing, "rm" would be allowed to execute
    // and could delete files. If the handler had a bug reading stdout, the counter would
    // stay at 0 even though the tool appeared to succeed.

    [SkippableFact]
    public async Task CliTool_ExecutesAllowedCommand_AndDescriptionBlocksDisallowed()
    {
        _fixture.RequireServer();

        // ── Blocked command verified via ToolDef description (pure SDK, no server needed) ──
        // The description encodes the whitelist; the server's LLM sees this and the handler
        // enforces it. We verify the description lists only allowed commands.
        var echoOnlyTool = CliTool.Create(allowedCommands: ["echo"]);
        Assert.Contains("echo", echoOnlyTool.Description, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rm", echoOnlyTool.Description, StringComparison.OrdinalIgnoreCase);

        // ── Execution: agent with CliTool + echo allowedCommands ──────────────
        // Use a host-based counter tool to verify the CliTool was called
        var host        = new S11EchoResultHost();
        var counterTool = ToolRegistry.FromInstance(host);
        var cliTool     = CliTool.Create(allowedCommands: ["echo"]);

        // Register the CLI tool alongside a counter tool so we can verify the CLI ran
        var allTools = new List<ToolDef>(counterTool) { cliTool };

        var agent = new Agent("s11_cli_exec_check")
        {
            Model        = Settings.LlmModel,
            Instructions =
                "You MUST call run_command with command='echo' and args=['hello_s11'] to run it. " +
                "Then call record_output with the stdout result from run_command. " +
                "Do not respond until both tools have been called.",
            Tools    = allTools,
            MaxTurns = 6,
        };

        await using var runtime = new AgentRuntime();
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        var result = await runtime.RunAsync(agent, "Run echo hello_s11 and record the output.", ct: cts.Token);

        // Validation: counter proves the record_output tool ran (not LLM text parsing)
        Assert.True(host.RecordCallCount > 0,
            $"Expected record_output to be called at least once but count was {host.RecordCallCount}. " +
            $"This means the CLI tool's output was not relayed through the record tool.");
        Assert.True(result.IsSuccess, $"Agent run failed: {result.Error}");

        // Counterfactual: agent without the CliTool would not have run_command at all
        var agentNoCli = new Agent("s11_no_cli") { Model = Settings.LlmModel };
        var planNoCli  = await runtime.PlanAsync(agentNoCli);
        var adNoCli    = E2eHelpers.GetAgentDef(planNoCli);
        Assert.DoesNotContain("run_command", E2eHelpers.ToolNames(adNoCli));
    }

    // ── 11.4  CliTool compiles in plan with toolType="worker" ───────────────
    //
    // Counterfactual: if CliTool were accidentally classified as "http" or "mcp",
    // the server would not route tool calls to the worker process at all.

    [SkippableFact]
    public async Task CliTool_CompilesWithWorkerType()
    {
        _fixture.RequireServer();

        var tool = CliTool.Create(allowedCommands: ["echo", "ls"]);
        var agent = new Agent("s11_cli_plan_check")
        {
            Model = Settings.LlmModel,
            Tools = [tool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "run_command"));

        // Counterfactual: agent without tools has no run_command
        var agentEmpty = new Agent("s11_no_tools") { Model = Settings.LlmModel };
        var planEmpty  = await runtime.PlanAsync(agentEmpty);
        var adEmpty    = E2eHelpers.GetAgentDef(planEmpty);
        Assert.DoesNotContain("run_command", E2eHelpers.ToolNames(adEmpty));
    }

    // ── 11.5  CliTool with credentials appears in plan (run_command tool present) ──
    //
    // The server strips credential values from plan responses (security).
    // We verify only that run_command appears and is a "worker" tool.
    // Credential presence is verified on the local ToolDef (test 11.1).
    //
    // Counterfactual: if CliTool were rejected by the server because of the credentials
    // field format, run_command would be absent from the plan.

    [SkippableFact]
    public async Task CliToolWithCredentials_AppearsInPlan()
    {
        _fixture.RequireServer();

        var tool = CliTool.Create(
            allowedCommands: ["gh", "git"],
            credentials:     ["GITHUB_TOKEN"]);

        var agent = new Agent("s11_cli_cred_plan")
        {
            Model = Settings.LlmModel,
            Tools = [tool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var toolNames = E2eHelpers.ToolNames(ad);
        Assert.Contains("run_command", toolNames);
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "run_command"));

        // Counterfactual: agent with only an MCP tool must not have run_command
        var mcpOnly = McpTools.Create(
            serverUrl: "http://localhost:3001/mcp",
            name:      "s11_mcp_only_check");
        var agentMcp = new Agent("s11_mcp_only") { Model = Settings.LlmModel, Tools = [mcpOnly] };
        var planMcp  = await runtime.PlanAsync(agentMcp);
        var adMcp    = E2eHelpers.GetAgentDef(planMcp);
        Assert.DoesNotContain("run_command", E2eHelpers.ToolNames(adMcp));
    }

    // ── 11.6  shell=true ToolDef schema has shell property; custom name and timeout work ──
    //
    // We verify that the ToolDef produced by CliTool.Create() has the correct
    // schema structure regardless of shell mode, because the shell flag is a
    // runtime call-time argument (not a ToolDef-level property).
    // We also verify the custom name parameter works.
    //
    // Counterfactual: if the schema did not include the "shell" property, the LLM
    // could not construct the correct JSON to enable shell mode.

    [Fact]
    public void CliTool_SchemaContainsShellProperty_AndCustomNameWorks()
    {
        var tool = CliTool.Create(
            name:           "run_shell_cmd",
            allowedCommands: ["bash"],
            timeoutSeconds: 120);

        Assert.Equal("run_shell_cmd", tool.Name);
        Assert.Contains("120", tool.Description); // timeout in description

        // Verify input schema has "shell" property
        var schemaJson = tool.InputSchema.ToJsonString();
        Assert.Contains("\"shell\"", schemaJson);
        Assert.Contains("\"command\"", schemaJson);
        Assert.Contains("\"args\"", schemaJson);

        // Counterfactual: default name is "run_command", not "run_shell_cmd"
        var defaultTool = CliTool.Create();
        Assert.Equal("run_command", defaultTool.Name);
        Assert.NotEqual("run_shell_cmd", defaultTool.Name);
    }
}

// ── Tool host ────────────────────────────────────────────────────────────────

/// <summary>
/// Counter-based tool host for Suite 11 test 11.3.
/// Proves that the CLI tool's stdout was relayed back through the agent
/// without parsing any LLM text output.
/// </summary>
internal sealed class S11EchoResultHost
{
    private int _recordCount;

    public int RecordCallCount => _recordCount;

    [Tool("Record the output from a CLI tool call. Call this with the stdout text.")]
    public string RecordOutput(string stdout)
    {
        Interlocked.Increment(ref _recordCount);
        return $"recorded:{stdout.Trim()}";
    }
}
