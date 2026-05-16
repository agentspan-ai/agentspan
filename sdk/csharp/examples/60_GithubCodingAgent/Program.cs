// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// GitHub Coding Agent — pick an issue, code the fix, create a PR.
//
// Uses explicit subprocess tools for all git/gh operations
// (compare 60a which uses LocalCodeExecution for all commands).
//
// Architecture (swarm):
//   coding_team (coordinator)
//   ├── github_agent  — picks issue, clones repo, commits, pushes, creates PR
//   ├── coder         — implements the fix (writes/reads files)
//   └── qa_tester     — reviews code, runs tests, approves or sends back
//
// Flow:
//   1. coding_team → github_agent (pick issue, clone, branch)
//   2. github_agent → coder (implement)
//   3. coder → qa_tester (review + test)
//   4. qa_tester → coder (if bugs) or → github_agent (if pass)
//   5. github_agent commits, pushes, creates PR → done
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment
//   - gh CLI authenticated: gh auth status
//   - Git configured with push access to the repo

using Agentspan;
using Agentspan.Examples;

const string Repo    = "agentspan/codingexamples";
var          WorkDir = $"/tmp/codingexamples-{Guid.NewGuid():N}"[..36];

// ── Tool sets per agent ────────────────────────────────────────

var githubTools = ToolRegistry.FromInstance(new GitHubTools(Repo, WorkDir));
var codingTools = ToolRegistry.FromInstance(new CodingTools(WorkDir));
var qaTools     = ToolRegistry.FromInstance(new QATools(WorkDir));

// ── GitHub Agent: handles all git/gh operations ────────────────

var githubAgent = new Agent("github_agent_60")
{
    Model                = Settings.LlmModel,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
    Tools                = [.. githubTools],
    Instructions         =
        "You are a GitHub operations specialist.\n\n" +
        $"Repo: {Repo}\nWork dir: {WorkDir}\n\n" +
        "IMPORTANT: Check conversation history. If [coder] and [qa_tester] messages " +
        "exist (especially 'ALL TESTS PASSED'), you are in PHASE 2 — skip to step 6.\n\n" +
        "PHASE 1 — SETUP (no [coder]/[qa_tester] messages yet):\n" +
        "1. Call list_github_issues to see open issues\n" +
        "2. Call get_github_issue to read the full details\n" +
        "3. Call clone_repo to clone the repository\n" +
        "4. Call git_create_branch with 'feature/issue-N-short-description'\n" +
        "5. Say 'transfer_to_coder' with the issue details.\n\n" +
        "PHASE 2 — PR CREATION (conversation contains QA approval):\n" +
        "6. Call git_commit_and_push to commit and push the changes\n" +
        "7. Call create_pull_request to create the PR (include issue_number to auto-close)\n" +
        "8. Output the PR URL. Do NOT transfer — workflow ends.",
};

// ── Coder: implements the fix ──────────────────────────────────

var coder = new Agent("coder_60")
{
    Model                = Settings.LlmModel,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
    Tools                = [.. codingTools],
    Instructions         =
        "You are an expert developer. Write clean, well-structured code.\n\n" +
        $"Repo cloned at: {WorkDir}\n\n" +
        "STEPS:\n" +
        "1. Call list_files to understand the repo structure\n" +
        "2. Write ALL files using write_file\n" +
        "3. Call read_file to verify your changes\n" +
        "4. Say 'transfer_to_qa_tester'\n\n" +
        "IF QA REPORTS BUGS: fix them, re-verify, say 'transfer_to_qa_tester' again.\n" +
        "You can ONLY transfer to qa_tester.",
};

// ── QA Tester: reviews code and runs tests ─────────────────────

var qaTester = new Agent("qa_tester_60")
{
    Model                = Settings.LlmModel,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
    Tools                = [.. qaTools],
    Instructions         =
        "You are a meticulous QA engineer. Review code for correctness and bugs.\n\n" +
        $"Repo at: {WorkDir}\n\n" +
        "1. Call read_file to review the code\n" +
        "2. Call list_files to check the repo structure\n" +
        "Test coverage: normal inputs, edge cases, boundary conditions.\n" +
        "If bugs found  → say 'transfer_to_coder' and describe the bugs clearly.\n" +
        "If all pass    → say 'transfer_to_github_agent' with a short QA approval summary.\n" +
        "NEVER say 'transfer_to_coding_team'.",
};

// ── Swarm coordinator ──────────────────────────────────────────

var codingTeam = new Agent("coding_team_60")
{
    Model          = Settings.LlmModel,
    Strategy       = Strategy.Swarm,
    Agents         = [githubAgent, coder, qaTester],
    MaxTurns       = 30,
    TimeoutSeconds = 900,
    Instructions   =
        "You are the coding team coordinator. Delegate to github_agent to start. " +
        "Say 'transfer_to_github_agent' now.",
};

// ── Run ───────────────────────────────────────────────────────

Console.WriteLine(new string('=', 60));
Console.WriteLine("  GitHub Coding Agent (Full)");
Console.WriteLine($"  Repo:     {Repo}");
Console.WriteLine($"  Work dir: {WorkDir}");
Console.WriteLine("  coding_team → github_agent ↔ coder ↔ qa_tester (swarm)");
Console.WriteLine(new string('=', 60));

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    codingTeam,
    "Pick an open issue from the GitHub repository, implement the fix, " +
    "get it reviewed by QA, and create a PR.");

result.PrintResult();

// ── Tool classes ──────────────────────────────────────────────

internal sealed class GitHubTools(string repo, string workDir)
{
    [Tool("List GitHub issues from the repository. state: open, closed, or all.")]
    public async Task<string> ListGithubIssues(string state = "open", int limit = 10)
        => await RunGhAsync([
            "issue", "list", "--repo", repo,
            "--state", state, "--limit", limit.ToString(),
            "--json", "number,title,body,labels",
        ]);

    [Tool("Get full details of a specific GitHub issue.")]
    public async Task<string> GetGithubIssue(int issueNumber)
        => await RunGhAsync([
            "issue", "view", issueNumber.ToString(), "--repo", repo,
            "--json", "number,title,body,labels,comments",
        ]);

    [Tool("Clone the GitHub repository to the working directory.")]
    public async Task<string> CloneRepo()
        => await RunProcessAsync("gh", ["repo", "clone", repo, workDir], cwd: null);

    [Tool("Create and checkout a new git branch in the working directory.")]
    public async Task<string> GitCreateBranch(string branchName)
        => await RunProcessAsync("git", ["checkout", "-b", branchName], cwd: workDir);

    [Tool("Stage all changes, commit with a message, and push to remote.")]
    public async Task<string> GitCommitAndPush(string message)
    {
        var add = await RunProcessAsync("git", ["add", "-A"], cwd: workDir);
        if (add.StartsWith("Error")) return add;
        var commit = await RunProcessAsync("git", ["commit", "-m", message], cwd: workDir);
        if (commit.StartsWith("Error")) return commit;
        return await RunProcessAsync("git", ["push", "-u", "origin", "HEAD"], cwd: workDir);
    }

    [Tool("Create a GitHub pull request. Pass issue_number > 0 to auto-close the issue.")]
    public async Task<string> CreatePullRequest(string title, string body, int issueNumber = 0)
    {
        var fullBody = issueNumber > 0 ? $"{body}\n\nCloses #{issueNumber}" : body;
        return await RunProcessAsync("gh",
            ["pr", "create", "--repo", repo, "--title", title, "--body", fullBody],
            cwd: workDir);
    }

    private Task<string> RunGhAsync(string[] args)
        => RunProcessAsync("gh", args, cwd: null);

    private static async Task<string> RunProcessAsync(string exe, string[] args, string? cwd)
    {
        using var proc = new System.Diagnostics.Process();
        proc.StartInfo = new System.Diagnostics.ProcessStartInfo
        {
            FileName               = exe,
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute        = false,
            WorkingDirectory       = cwd ?? "",
        };
        foreach (var a in args) proc.StartInfo.ArgumentList.Add(a);
        try
        {
            proc.Start();
            var stdout = await proc.StandardOutput.ReadToEndAsync();
            var stderr = await proc.StandardError.ReadToEndAsync();
            await proc.WaitForExitAsync();
            return proc.ExitCode == 0
                ? (stdout.Trim() is { Length: > 0 } s ? s : "OK")
                : $"Error: {stderr.Trim()}";
        }
        catch (Exception ex) { return $"Error: {ex.Message}"; }
    }
}

internal sealed class CodingTools(string workDir)
{
    [Tool("Write content to a file in the cloned repo. path is relative to the repo root.")]
    public string WriteFile(string path, string content)
    {
        var full = System.IO.Path.Combine(workDir, path);
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(full)!);
        System.IO.File.WriteAllText(full, content);
        return $"Wrote {content.Length} bytes to {path}";
    }

    [Tool("Read a file from the cloned repo. path is relative to the repo root.")]
    public string ReadFile(string path)
    {
        var full = System.IO.Path.Combine(workDir, path);
        return System.IO.File.Exists(full) ? System.IO.File.ReadAllText(full) : $"File not found: {path}";
    }

    [Tool("List files in a directory of the cloned repo. path is relative to the repo root.")]
    public string ListFiles(string path = ".")
    {
        var full = System.IO.Path.Combine(workDir, path);
        if (!System.IO.Directory.Exists(full)) return $"Not a directory: {path}";
        var prefix = workDir.TrimEnd('/') + "/";
        return string.Join("\n", System.IO.Directory
            .GetFiles(full, "*", System.IO.SearchOption.AllDirectories)
            .Where(f => !f.Contains("/.git/"))
            .Select(f => f.StartsWith(prefix) ? f[prefix.Length..] : f));
    }
}

internal sealed class QATools(string workDir)
{
    [Tool("Read a file from the cloned repo. path is relative to the repo root.")]
    public string ReadFile(string path)
    {
        var full = System.IO.Path.Combine(workDir, path);
        return System.IO.File.Exists(full) ? System.IO.File.ReadAllText(full) : $"File not found: {path}";
    }

    [Tool("List files in a directory of the cloned repo. path is relative to the repo root.")]
    public string ListFiles(string path = ".")
    {
        var full = System.IO.Path.Combine(workDir, path);
        if (!System.IO.Directory.Exists(full)) return $"Not a directory: {path}";
        var prefix = workDir.TrimEnd('/') + "/";
        return string.Join("\n", System.IO.Directory
            .GetFiles(full, "*", System.IO.SearchOption.AllDirectories)
            .Where(f => !f.Contains("/.git/"))
            .Select(f => f.StartsWith(prefix) ? f[prefix.Length..] : f));
    }
}
