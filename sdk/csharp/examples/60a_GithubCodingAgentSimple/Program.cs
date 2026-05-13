// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// GitHub Coding Agent (simplified) — pick an issue, code the fix, create a PR.
//
// Uses LocalCodeExecution=true so agents run git/gh CLI commands directly
// — no custom tool definitions needed.
//
// Architecture (swarm):
//   coding_team (coordinator)
//   ├── github_agent  — picks issue, clones repo, commits, pushes, creates PR
//   ├── coder         — implements the fix
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
//   - Agentspan server with code execution support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - gh CLI authenticated: gh auth status
//   - Git configured with push access to the repo

using Agentspan;
using Agentspan.Examples;

const string Repo    = "agentspan/codingexamples";
var          WorkDir = $"/tmp/codingexamples-{Guid.NewGuid():N}"[..36];

// ── GitHub Agent ──────────────────────────────────────────────

var githubAgent = new Agent("github_agent_60a")
{
    Model                = Settings.LlmModel,
    LocalCodeExecution   = true,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
    Instructions         =
        "You are a GitHub operations specialist.\n\n" +
        $"Repo: {Repo}\nWork dir: {WorkDir}\n\n" +
        "IMPORTANT: Check conversation history. If [coder] and [qa_tester] messages " +
        "exist (especially 'ALL TESTS PASSED'), you are in PHASE 2 — skip to step 6.\n\n" +
        "PHASE 1 — SETUP (no [coder]/[qa_tester] messages yet):\n" +
        $"1. gh issue list --repo {Repo} --state open --json number,title,body\n" +
        "2. Pick the most suitable issue\n" +
        $"3. gh repo clone {Repo} {WorkDir}\n" +
        $"4. cd {WorkDir} && git checkout -b feature/issue-N-description\n" +
        "5. Say 'transfer_to_coder' with the issue details.\n\n" +
        "PHASE 2 — PR CREATION:\n" +
        $"6. cd {WorkDir} && git add -A && git commit -m 'Fix #N: description' && git push -u origin HEAD\n" +
        $"7. gh pr create --repo {Repo} --title 'Fix #N: title' --body 'Closes #N'\n" +
        "8. Output the PR URL. Do NOT transfer — workflow ends.",
};

// ── Coder ─────────────────────────────────────────────────────

var coder = new Agent("coder_60a")
{
    Model                = Settings.LlmModel,
    LocalCodeExecution   = true,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
    Instructions         =
        "You are an expert developer. Write clean, well-structured code.\n\n" +
        $"Repo cloned at: {WorkDir}\n\n" +
        "STEPS:\n" +
        $"1. Explore: find {WorkDir} -type f -not -path '*/.git/*'\n" +
        "2. Write ALL files in a single bash block using heredocs\n" +
        "3. Test your code to verify it works\n" +
        "4. Say 'transfer_to_qa_tester'\n\n" +
        "IF QA REPORTS BUGS: fix them, re-test, say 'transfer_to_qa_tester' again.\n" +
        "You can ONLY transfer to qa_tester.",
};

// ── QA Tester ─────────────────────────────────────────────────

var qaTester = new Agent("qa_tester_60a")
{
    Model                = Settings.LlmModel,
    LocalCodeExecution   = true,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
    Instructions         =
        "You are a meticulous QA engineer. Review code for correctness and bugs.\n\n" +
        $"Repo at: {WorkDir}\n\n" +
        "Test coverage: normal inputs, edge cases, boundary conditions.\n" +
        "If bugs found → say 'transfer_to_coder'\n" +
        "If all pass  → say 'transfer_to_github_agent'\n" +
        "NEVER say 'transfer_to_coding_team'.",
};

// ── Swarm coordinator ─────────────────────────────────────────

var codingTeam = new Agent("coding_team_60a")
{
    Model        = Settings.LlmModel,
    Strategy     = Strategy.Swarm,
    Agents       = [githubAgent, coder, qaTester],
    MaxTurns     = 30,
    TimeoutSeconds = 900,
    Instructions =
        "You are the coding team coordinator. Delegate to github_agent to start. " +
        "Say 'transfer_to_github_agent' now.",
};

// ── Run ───────────────────────────────────────────────────────

Console.WriteLine(new string('=', 60));
Console.WriteLine("  GitHub Coding Agent (Simplified)");
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
