// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 7 — Credentials: external tool flag and credential declaration.
//
// Corresponds to example: 16h_CredentialsExternalWorker
//
// Design note (discovered during test authoring):
//   In C#, external tools must be created as ToolDef objects directly with
//   External = true and Credentials = [...]. ToolRegistry.FromInstance()
//   explicitly skips [Tool(External=true)] methods because they have no
//   local handler. This is correct by design — external tools dispatch to
//   a separate Conductor worker process.
//
// Two validation layers:
//   [Fact]          — pure SDK tests, no server. Inspect ToolDef properties.
//   [SkippableFact] — server tests. Verify the compiled plan structure.
//
// What the server does:
//   - External tools are compiled as Conductor task references and appear
//     in agentDef.tools with toolType "external".
//   - Credential key names may be stripped from plan responses for security.
//     We test via the local ToolDef object where possible.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.Json.Nodes;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite7_Credentials
{
    private readonly E2eFixture _fixture;

    public Suite7_Credentials(E2eFixture fixture) => _fixture = fixture;

    // ── 7.1  External ToolDef has External=true and credentials ──────────

    [Fact]
    public void ExternalToolDef_HasExternalFlagAndCredentials()
    {
        var tool = new ToolDef
        {
            Name        = "github_lookup",
            Description = "Look up a GitHub user. Runs on an external worker.",
            External    = true,
            Credentials = ["GITHUB_TOKEN"],
            InputSchema = new JsonObject
            {
                ["type"] = "object",
                ["properties"] = new JsonObject
                {
                    ["username"] = new JsonObject { ["type"] = "string" },
                },
                ["required"] = new JsonArray { "username" },
            },
        };

        Assert.Equal("github_lookup", tool.Name);
        Assert.True(tool.External, "External=true must be reflected on the ToolDef.");
        Assert.Contains("GITHUB_TOKEN", tool.Credentials);

        // Counterfactual: a ToolDef without External=true must have External=false
        var localTool = new ToolDef
        {
            Name        = "local_lookup",
            Description = "Local lookup.",
            InputSchema = new JsonObject(),
        };
        Assert.False(localTool.External, "Default ToolDef must not have External=true.");
        Assert.Empty(localTool.Credentials);
    }

    // ── 7.2  Multiple credentials on an external ToolDef ─────────────────

    [Fact]
    public void ExternalToolDef_MultipleCredentialsAllPresent()
    {
        var tool = new ToolDef
        {
            Name        = "multi_cred_tool",
            Description = "A tool needing two credentials.",
            External    = true,
            Credentials = ["GITHUB_TOKEN", "SLACK_TOKEN"],
            InputSchema = new JsonObject(),
        };

        Assert.Contains("GITHUB_TOKEN", tool.Credentials);
        Assert.Contains("SLACK_TOKEN",  tool.Credentials);
        Assert.Equal(2, tool.Credentials.Length);

        // Counterfactual: single-credential ToolDef must not include SLACK_TOKEN
        var singleCred = new ToolDef
        {
            Name        = "single_cred",
            Description = "Single credential.",
            External    = true,
            Credentials = ["GITHUB_TOKEN"],
            InputSchema = new JsonObject(),
        };
        Assert.DoesNotContain("SLACK_TOKEN", singleCred.Credentials);
    }

    // ── 7.3  Agent with external ToolDef compiles on the server ──────────

    [SkippableFact]
    public async Task ExternalToolDef_AgentCompilesAndToolInPlan()
    {
        _fixture.RequireServer();

        var externalTool = new ToolDef
        {
            Name        = "s7_github_lookup",
            Description = "Look up a GitHub user. Runs on an external worker.",
            External    = true,
            Credentials = ["GITHUB_TOKEN"],
            InputSchema = new JsonObject
            {
                ["type"] = "object",
                ["properties"] = new JsonObject
                {
                    ["username"] = new JsonObject { ["type"] = "string" },
                },
                ["required"] = new JsonArray { "username" },
            },
        };

        var agent = new Agent("s7_ext_tool_compile")
        {
            Model = Settings.LlmModel,
            Tools = [externalTool],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);

        Assert.NotNull(plan);
        Assert.True(plan!["workflowDef"] is not null, "Plan must include workflowDef.");

        var ad        = E2eHelpers.GetAgentDef(plan);
        var toolNames = E2eHelpers.ToolNames(ad);
        Assert.Contains("s7_github_lookup", toolNames);

        // Tool type must be "external" in the compiled plan
        var toolType = E2eHelpers.GetToolType(ad, "s7_github_lookup");
        Assert.Equal("external", toolType);

        // Counterfactual: a local tool on the same agent must have toolType "worker"
        var localTool = ToolDefFactory.Create(
            name:        "s7_local_tool",
            description: "A local worker tool.",
            handler:     (_, _) => Task.FromResult<object?>("ok"));
        var agentMixed = new Agent("s7_mixed_types")
        {
            Model = Settings.LlmModel,
            Tools = [externalTool, localTool],
        };
        var planMixed = await runtime.PlanAsync(agentMixed);
        var adMixed   = E2eHelpers.GetAgentDef(planMixed);
        Assert.Equal("external", E2eHelpers.GetToolType(adMixed, "s7_github_lookup"));
        Assert.Equal("worker",   E2eHelpers.GetToolType(adMixed, "s7_local_tool"));
    }

    // ── 7.4  Local credential tool (worker, not external) appears in plan ─

    [SkippableFact]
    public async Task LocalCredentialTool_AppearsInPlanWithWorkerType()
    {
        _fixture.RequireServer();

        var agent = new Agent("s7_local_cred_tool")
        {
            Model = Settings.LlmModel,
            Tools = ToolRegistry.FromInstance(new S7LocalCredToolHost()),
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // Worker tool with credentials appears with toolType "worker"
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "cred_worker_tool"));

        // Counterfactual: agent without tools has no tools in the plan
        var agentNoTools = new Agent("s7_no_tools") { Model = Settings.LlmModel };
        var planNoTools  = await runtime.PlanAsync(agentNoTools);
        var adNoTools    = E2eHelpers.GetAgentDef(planNoTools);
        Assert.DoesNotContain("cred_worker_tool", E2eHelpers.ToolNames(adNoTools));
    }
}

// ── Tool hosts ──────────────────────────────────────────────────────────────

internal sealed class S7LocalCredToolHost
{
    [Tool("Fetch data using a stored credential.", Credentials = ["API_KEY"])]
    public string CredWorkerTool(string query) => $"result for {query}";
}
