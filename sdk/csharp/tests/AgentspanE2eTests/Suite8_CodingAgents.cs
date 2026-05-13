// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 8 — GitHub Coding Agents: plan structure and local tool execution.
//
// Corresponds to examples:
//   60_GithubCodingAgent         — swarm with explicit subprocess tools
//   61_GithubCodingAgentChained  — sequential pipeline with CliTool + credentials
//
// Validation strategy:
//   - Plan tests (8.1–8.5): PlanAsync() only — no LLM, no GitHub auth, no gh CLI.
//   - Execution test (8.6): local file tools with Interlocked counter — no LLM parsing.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Threading;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite8_CodingAgents
{
    private readonly E2eFixture _fixture;

    public Suite8_CodingAgents(E2eFixture fixture) => _fixture = fixture;

    // ── 8.1  Swarm coordinator has swarm strategy and correct sub-agent count ──

    [SkippableFact]
    public async Task CodingSwarm_StrategyAndSubAgentCountInPlan()
    {
        _fixture.RequireServer();

        var githubAgent = new Agent("s8_github_agent") { Model = Settings.LlmModel, Instructions = "GitHub ops." };
        var coder       = new Agent("s8_coder")        { Model = Settings.LlmModel, Instructions = "Write code." };
        var qaTester    = new Agent("s8_qa_tester")    { Model = Settings.LlmModel, Instructions = "Test code." };

        var codingTeam = new Agent("s8_coding_team")
        {
            Model    = Settings.LlmModel,
            Strategy = Strategy.Swarm,
            Agents   = [githubAgent, coder, qaTester],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(codingTeam);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var strategy = ad["strategy"]?.GetValue<string>();
        Assert.Equal("swarm", strategy, ignoreCase: true);

        var subAgents = E2eHelpers.SubAgentNames(ad);
        Assert.Equal(3, subAgents.Count);
        Assert.Contains("s8_github_agent", subAgents);
        Assert.Contains("s8_coder",        subAgents);
        Assert.Contains("s8_qa_tester",    subAgents);

        // Counterfactual: a swarm with 2 sub-agents must not show count 3
        var smallTeam = new Agent("s8_small_team")
        {
            Model    = Settings.LlmModel,
            Strategy = Strategy.Swarm,
            Agents   = [githubAgent, coder],
        };
        var planSmall   = await runtime.PlanAsync(smallTeam);
        var adSmall     = E2eHelpers.GetAgentDef(planSmall);
        var smallAgents = E2eHelpers.SubAgentNames(adSmall);
        Assert.NotEqual(3, smallAgents.Count);
    }

    // ── 8.2  GitHub coding agent tools appear in plan ────────────────────

    [SkippableFact]
    public async Task GithubAgent_ToolsRegisteredInPlan()
    {
        _fixture.RequireServer();

        var host  = new S8GitHubToolHost("/tmp/s8_work", "agentspan/test");
        var agent = new Agent("s8_github_tools_check")
        {
            Model = Settings.LlmModel,
            Tools = ToolRegistry.FromInstance(host),
        };

        await using var runtime = new AgentRuntime();
        var plan      = await runtime.PlanAsync(agent);
        var ad        = E2eHelpers.GetAgentDef(plan);
        var toolNames = E2eHelpers.ToolNames(ad);

        Assert.Contains("list_github_issues",  toolNames);
        Assert.Contains("get_github_issue",     toolNames);
        Assert.Contains("clone_repo",           toolNames);
        Assert.Contains("git_create_branch",    toolNames);
        Assert.Contains("git_commit_and_push",  toolNames);
        Assert.Contains("create_pull_request",  toolNames);

        // Counterfactual: an agent with no tools has an empty tool list
        var agentNoTools = new Agent("s8_no_tools") { Model = Settings.LlmModel };
        var planNoTools  = await runtime.PlanAsync(agentNoTools);
        var adNoTools    = E2eHelpers.GetAgentDef(planNoTools);
        var emptyNames   = E2eHelpers.ToolNames(adNoTools);
        Assert.DoesNotContain("list_github_issues", emptyNames);
    }

    // ── 8.3  CliTool.Create() with credentials: ToolDef and plan checks ─────
    //
    // The server strips credential names from plan responses (security).
    // We split this into two layers:
    //   [Fact]          — verify ToolDef.Credentials on the local object.
    //   [SkippableFact] — verify run_command appears in the compiled plan.

    [Fact]
    public void CliToolWithCredentials_ToolDefHasCredentials()
    {
        var fetchCli = CliTool.Create(
            allowedCommands: ["gh", "git", "mktemp"],
            timeoutSeconds:  60,
            credentials:     ["GITHUB_TOKEN", "GH_TOKEN"]);

        Assert.Equal("run_command", fetchCli.Name);
        Assert.Contains("GITHUB_TOKEN", fetchCli.Credentials);
        Assert.Contains("GH_TOKEN",     fetchCli.Credentials);

        // Counterfactual: CliTool without credentials has empty credentials
        var cliNoCred = CliTool.Create(allowedCommands: ["ls"]);
        Assert.Empty(cliNoCred.Credentials);
    }

    [SkippableFact]
    public async Task CliToolWithCredentials_AppearsInPlanAsWorker()
    {
        _fixture.RequireServer();

        var fetchCli = CliTool.Create(
            allowedCommands: ["gh", "git", "mktemp"],
            timeoutSeconds:  60,
            credentials:     ["GITHUB_TOKEN", "GH_TOKEN"]);

        var agent = new Agent("s8_cli_plan_check")
        {
            Model = Settings.LlmModel,
            Tools = [fetchCli],
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(agent);
        var ad   = E2eHelpers.GetAgentDef(plan);

        // CliTool appears in the plan as a worker tool
        Assert.Equal("worker", E2eHelpers.GetToolType(ad, "run_command"));

        // Counterfactual: agent without tools has no run_command
        var agentEmpty = new Agent("s8_cli_empty") { Model = Settings.LlmModel };
        var planEmpty  = await runtime.PlanAsync(agentEmpty);
        var adEmpty    = E2eHelpers.GetAgentDef(planEmpty);
        Assert.DoesNotContain("run_command", E2eHelpers.ToolNames(adEmpty));
    }

    // ── 8.4  >> operator creates sequential pipeline with all stages ──────

    [SkippableFact]
    public async Task ChainedPipeline_SequentialStrategyInPlan()
    {
        _fixture.RequireServer();

        var fetchIssues = new Agent("s8_fetch_issues") { Model = Settings.LlmModel, Instructions = "Fetch issues." };
        var codingQa    = new Agent("s8_coding_qa")    { Model = Settings.LlmModel, Instructions = "Code and QA." };
        var pushPr      = new Agent("s8_push_pr")      { Model = Settings.LlmModel, Instructions = "Create PR." };

        var pipeline = fetchIssues >> codingQa >> pushPr;

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(pipeline);
        var ad   = E2eHelpers.GetAgentDef(plan);

        var strategy  = ad["strategy"]?.GetValue<string>();
        Assert.Equal("sequential", strategy, ignoreCase: true);

        var subAgents = E2eHelpers.SubAgentNames(ad);
        Assert.True(subAgents.Count >= 3,
            $"Expected >= 3 stages in the pipeline but got {subAgents.Count}.");

        // Counterfactual: a swarm must not have sequential strategy
        var swarm = new Agent("s8_swarm_check")
        {
            Model    = Settings.LlmModel,
            Strategy = Strategy.Swarm,
            Agents   = [fetchIssues, codingQa, pushPr],
        };
        var planSwarm   = await runtime.PlanAsync(swarm);
        var adSwarm     = E2eHelpers.GetAgentDef(planSwarm);
        var swarmStrat  = adSwarm["strategy"]?.GetValue<string>();
        Assert.NotEqual("sequential", swarmStrat, StringComparer.OrdinalIgnoreCase);
    }

    // ── 8.5  TextMentionTermination on a pipeline stage appears in plan ───

    [SkippableFact]
    public async Task ChainedPipeline_TerminationOnStageInPlan()
    {
        _fixture.RequireServer();

        // Test the fetch stage directly — it has the NO_OPEN_ISSUES gate
        var fetchStage = new Agent("s8_fetch_term_check")
        {
            Model       = Settings.LlmModel,
            MaxTurns    = 20,
            Termination = new TextMentionTermination("NO_OPEN_ISSUES"),
            Instructions = "Fetch issues.",
        };

        await using var runtime = new AgentRuntime();
        var plan = await runtime.PlanAsync(fetchStage);
        var ad   = E2eHelpers.GetAgentDef(plan);

        Assert.True(ad["termination"] is not null,
            "Agent with TextMentionTermination must have a termination block in the plan.");

        // Counterfactual: an agent without termination has null termination
        var noTermStage = new Agent("s8_no_term_check")
        {
            Model    = Settings.LlmModel,
            MaxTurns = 20,
        };
        var planNoTerm = await runtime.PlanAsync(noTermStage);
        var adNoTerm   = E2eHelpers.GetAgentDef(planNoTerm);
        Assert.True(adNoTerm["termination"] is null,
            "Agent without termination must have null termination block.");
    }

    // ── 8.6  Local file tools execute (no LLM text parsing) ──────────────
    //
    // Tests the write_file / read_file / list_files pattern from example 60.
    // Uses a temp directory so no GitHub auth is required.

    [SkippableFact]
    public async Task LocalFileTools_Execute()
    {
        _fixture.RequireServer();

        var tmpDir = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(), $"s8_file_test_{Guid.NewGuid():N}");
        System.IO.Directory.CreateDirectory(tmpDir);

        try
        {
            var host  = new S8FileToolHost(tmpDir);
            var tools = ToolRegistry.FromInstance(host);

            var agent = new Agent("s8_file_tools_exec")
            {
                Model        = Settings.LlmModel,
                Instructions =
                    "You MUST call write_file to create a file named 'hello.txt' with " +
                    "content 'sentinel-s8', then call read_file to read it back. " +
                    "Do not respond until both tools have been called.",
                Tools    = tools,
                MaxTurns = 6,
            };

            await using var runtime = new AgentRuntime();
            using var cts   = new CancellationTokenSource(TimeSpan.FromSeconds(120));
            var result = await runtime.RunAsync(agent, "Write and read a test file.", ct: cts.Token);

            // Validation: tool call counters, not LLM output text
            Assert.True(host.WriteCallCount > 0,
                $"Expected write_file to be called at least once but count was {host.WriteCallCount}.");
            Assert.True(host.ReadCallCount > 0,
                $"Expected read_file to be called at least once but count was {host.ReadCallCount}.");
            Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
        }
        finally
        {
            if (System.IO.Directory.Exists(tmpDir))
                System.IO.Directory.Delete(tmpDir, recursive: true);
        }
    }
}

// ── Tool hosts ──────────────────────────────────────────────────────────────

/// <summary>Mirrors the GitHubTools class from example 60 but without subprocess calls.</summary>
internal sealed class S8GitHubToolHost(string workDir, string repo)
{
    [Tool("List GitHub issues from the repository.")]
    public string ListGithubIssues(string state = "open", int limit = 10)
        => $"[stub] would list {limit} {state} issues from {repo}";

    [Tool("Get full details of a specific GitHub issue.")]
    public string GetGithubIssue(int issueNumber)
        => $"[stub] would get issue #{issueNumber} from {repo}";

    [Tool("Clone the GitHub repository to the working directory.")]
    public string CloneRepo()
        => $"[stub] would clone {repo} to {workDir}";

    [Tool("Create and checkout a new git branch in the working directory.")]
    public string GitCreateBranch(string branchName)
        => $"[stub] would create branch {branchName}";

    [Tool("Stage all changes, commit with a message, and push to remote.")]
    public string GitCommitAndPush(string message)
        => $"[stub] would commit and push: {message}";

    [Tool("Create a GitHub pull request. Pass issue_number > 0 to auto-close the issue.")]
    public string CreatePullRequest(string title, string body, int issueNumber = 0)
        => $"[stub] would create PR: {title}";
}

/// <summary>Mirrors the CodingTools class from example 60 using Interlocked counters.</summary>
internal sealed class S8FileToolHost(string workDir)
{
    private int _writeCount;
    private int _readCount;
    private int _listCount;

    public int WriteCallCount => _writeCount;
    public int ReadCallCount  => _readCount;
    public int ListCallCount  => _listCount;

    [Tool("Write content to a file. path is relative to the work directory.")]
    public string WriteFile(string path, string content)
    {
        Interlocked.Increment(ref _writeCount);
        var full = System.IO.Path.Combine(workDir, path);
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(full)!);
        System.IO.File.WriteAllText(full, content);
        return $"Wrote {content.Length} bytes to {path}";
    }

    [Tool("Read a file from the work directory. path is relative to the work directory.")]
    public string ReadFile(string path)
    {
        Interlocked.Increment(ref _readCount);
        var full = System.IO.Path.Combine(workDir, path);
        return System.IO.File.Exists(full) ? System.IO.File.ReadAllText(full) : $"File not found: {path}";
    }

    [Tool("List files in a directory of the work directory.")]
    public string ListFiles(string path = ".")
    {
        Interlocked.Increment(ref _listCount);
        var full = System.IO.Path.Combine(workDir, path);
        if (!System.IO.Directory.Exists(full)) return $"Not a directory: {path}";
        return string.Join("\n", System.IO.Directory.GetFiles(full, "*", System.IO.SearchOption.AllDirectories));
    }
}
