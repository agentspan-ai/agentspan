// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// GitHub Coding Agent — issue to PR pipeline.
//
// A three-stage sequential pipeline using CliTool for gh/git commands:
//   Stage 1: git_fetch_issues — list open issues, pick one, push an empty branch
//   Stage 2: coding_qa (swarm) — coder implements the fix, qa_tester reviews
//   Stage 3: git_push_pr — create the pull request
//
// Each stage receives the previous stage's output as its input (>> operator).
// TextMentionTermination("NO_OPEN_ISSUES") stops the pipeline early if there
// are no open issues (equivalent to Python's gate=TextGate("NO_OPEN_ISSUES")).
//
// Since C# has no stop_when callback, each stage uses MaxTurns to bound
// execution. Stage 1 outputs structured text (REPO:/BRANCH:/ISSUE:/etc.) that
// stage 2 reads, and stage 2 outputs REPO/BRANCH/SUMMARY for stage 3.
//
// Setup (one-time):
//   agentspan credentials set GITHUB_TOKEN <your-github-token>
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment
//   - GITHUB_TOKEN stored via `agentspan credentials set`
//   - gh CLI installed

using Agentspan;
using Agentspan.Examples;

const string Repo  = "agentspan-ai/codingexamples";
const string Model = "anthropic/claude-sonnet-4-6";

// ── Stage 1: Fetch issues ─────────────────────────────────────

var fetchCli = CliTool.Create(
    allowedCommands: ["gh", "git", "mktemp", "ls"],
    timeoutSeconds:  60,
    credentials:     ["GITHUB_TOKEN", "GH_TOKEN"]);

var gitFetchIssues = new Agent("git_fetch_issues_61")
{
    Model       = Model,
    MaxTokens   = 8192,
    MaxTurns    = 20,
    Tools       = [fetchCli],
    Termination = new TextMentionTermination("NO_OPEN_ISSUES"),
    Instructions = $"""
        You fetch ONE open issue from {Repo} and push an empty branch.

        Step 1 — list open issues:
          run_command: gh issue list --repo {Repo} --state open --limit 5
        If there are no open issues, respond with ONLY: NO_OPEN_ISSUES

        Step 2 — pick an issue and fetch its FULL details (body, author, labels):
          run_command: gh issue view <N> --repo {Repo} --json number,title,body,author,labels
        Read the JSON output carefully — extract the author login and the COMPLETE body.

        Step 3 — create a branch and push it (use shell=true for the compound command):
          TMPDIR=$(mktemp -d) && gh repo clone {Repo} "$TMPDIR" && cd "$TMPDIR" && git checkout -b fix/issue-<N> && git push -u origin fix/issue-<N> && echo "DONE"

        Step 4 — respond with ONLY these lines (no further tool calls):
          REPO: {Repo}
          BRANCH: fix/issue-<N>
          ISSUE: #<N> <title>
          AUTHOR: <who opened the issue>
          DETAILS: <full issue body — preserve all requirements and context>
          SUMMARY: <one-sentence description>

        RULES:
        - Do NOT create files, commits, or pull requests.
        - After step 3, stop using tools. Just output the structured text.
        - Include the COMPLETE issue body in DETAILS — the next stage needs it.
        """,
};

// ── Stage 2: Coding + QA (swarm) ──────────────────────────────

var codingCli = CliTool.Create(
    allowedCommands: ["gh", "git", "mktemp", "rm", "ls", "cat", "mkdir", "cp"],
    timeoutSeconds:  120,
    credentials:     ["GITHUB_TOKEN", "GH_TOKEN"]);

var coder = new Agent("coder_61")
{
    Model        = Model,
    MaxTokens    = 60_000,
    Tools        = [codingCli],
    Instructions = """
        You are a senior developer. Your input contains issue details from the
        previous stage including REPO, BRANCH, ISSUE, AUTHOR, DETAILS, SUMMARY.

        1. Read DETAILS carefully — it contains the full issue body and requirements.
        2. Clone the repo: gh repo clone <REPO> /tmp/work && cd /tmp/work
        3. Check out the branch: git checkout <BRANCH>
        4. Implement the fix according to ALL requirements in DETAILS.
        5. Commit and push your changes.
        6. Say HANDOFF_TO_QA with REPO, BRANCH, and a summary of CHANGES.
        """,
};

var qaTester = new Agent("qa_tester_61")
{
    Model        = Model,
    MaxTokens    = 60_000,
    MaxTurns     = 15,
    Tools        = [codingCli],
    Instructions = """
        You are a QA engineer. Clone the repo, check out the branch, review changes, run tests.
        If bugs found: say HANDOFF_TO_CODER with what to fix.
        If good: say QA_APPROVED with REPO, BRANCH, and SUMMARY.
        """,
};

var codingQa = new Agent("coding_qa_61")
{
    Model          = Model,
    Strategy       = Strategy.Swarm,
    Agents         = [coder, qaTester],
    MaxTurns       = 200,
    MaxTokens      = 60_000,
    TimeoutSeconds = 6000,
    Instructions   =
        "Delegate to coder, then qa_tester. Loop until QA approves. " +
        "Output REPO/BRANCH/SUMMARY when done.",
};

// ── Stage 3: Create PR ────────────────────────────────────────

var prCli = CliTool.Create(
    allowedCommands: ["gh", "git"],
    timeoutSeconds:  60,
    credentials:     ["GITHUB_TOKEN", "GH_TOKEN"]);

var gitPushPr = new Agent("git_push_pr_61")
{
    Model        = Model,
    MaxTokens    = 8192,
    MaxTurns     = 15,
    Tools        = [prCli],
    Instructions = """
        Create a pull request. Extract REPO, BRANCH, and ISSUE from the previous stage output.

        Run (use shell=true so shell quoting is handled correctly):
          gh pr create --repo <REPO> --base main --head <BRANCH> --title "Fix <ISSUE>" --body "Fixes <ISSUE>"

        After the command succeeds, STOP calling tools and respond with ONLY the PR URL.
        """,
};

// ── Pipeline ──────────────────────────────────────────────────

var pipeline = gitFetchIssues >> codingQa >> gitPushPr;

// ── Run ───────────────────────────────────────────────────────

Console.WriteLine(new string('=', 60));
Console.WriteLine("  GitHub Coding Agent (Chained Pipeline)");
Console.WriteLine($"  Repo: {Repo}");
Console.WriteLine("  git_fetch_issues >> coding_qa (swarm) >> git_push_pr");
Console.WriteLine(new string('=', 60));

using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(60));
await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    pipeline,
    "Pick an open issue and create a PR.",
    ct: cts.Token);

result.PrintResult();
