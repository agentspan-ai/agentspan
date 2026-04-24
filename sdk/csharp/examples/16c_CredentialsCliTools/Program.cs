// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Credentials — CLI tools with credential injection.
//
// Demonstrates:
//   - [Tool(Credentials = ["GITHUB_TOKEN"])] on a class method
//   - The SDK injects GITHUB_TOKEN into the process environment
//     before each tool invocation (inherited by child processes)
//   - Spawning a subprocess (`gh`) that picks up the injected env var
//   - Multi-credential tools: declare all required env vars
//
// When the tool runs, the declared credentials are resolved from the
// server's credential store and set as env vars via
// Environment.SetEnvironmentVariable. Child processes spawned via
// Process.Start() inherit the environment automatically.
//
// Setup (one-time):
//   agentspan credentials set GITHUB_TOKEN <your-github-token>
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - GITHUB_TOKEN stored via `agentspan credentials set`
//   - gh CLI installed (https://cli.github.com)

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("devops_agent_16c")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new GitHubCliTools()),
    Instructions =
        "You are a DevOps assistant. You can list GitHub pull requests " +
        "using the gh_list_prs tool. GITHUB_TOKEN is automatically available.",
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    agent,
    "List the open pull requests for agentspan-ai/agentspan.");
result.PrintResult();

// ── Tool class ─────────────────────────────────────────────────────────

internal sealed class GitHubCliTools
{
    // GITHUB_TOKEN is injected into Environment by the SDK before this runs.
    // The child process (gh) inherits the env and picks it up as GH_TOKEN.
    [Tool("List open pull requests for a GitHub repo using the gh CLI. repo format: 'owner/repo'",
          Credentials = ["GITHUB_TOKEN"])]
    public async Task<Dictionary<string, object>> GhListPrs(
        string repo, string state = "open")
    {
        // Propagate GITHUB_TOKEN as GH_TOKEN for `gh` CLI auth
        var token = Environment.GetEnvironmentVariable("GITHUB_TOKEN") ?? "";
        if (string.IsNullOrEmpty(token))
            return new() { ["error"] = "GITHUB_TOKEN not found — run: agentspan credentials set GITHUB_TOKEN <your-token>" };

        using var proc = new System.Diagnostics.Process();
        proc.StartInfo = new System.Diagnostics.ProcessStartInfo
        {
            FileName               = "gh",
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute        = false,
        };
        proc.StartInfo.ArgumentList.Add("pr");
        proc.StartInfo.ArgumentList.Add("list");
        proc.StartInfo.ArgumentList.Add("--repo");  proc.StartInfo.ArgumentList.Add(repo);
        proc.StartInfo.ArgumentList.Add("--state"); proc.StartInfo.ArgumentList.Add(state);
        proc.StartInfo.ArgumentList.Add("--limit"); proc.StartInfo.ArgumentList.Add("5");
        proc.StartInfo.ArgumentList.Add("--json");  proc.StartInfo.ArgumentList.Add("number,title,state,url");

        // gh CLI reads GH_TOKEN (not GITHUB_TOKEN) for authentication
        proc.StartInfo.Environment["GH_TOKEN"] = token;

        try
        {
            proc.Start();
            var stdout = await proc.StandardOutput.ReadToEndAsync();
            var stderr = await proc.StandardError.ReadToEndAsync();
            await proc.WaitForExitAsync();

            if (proc.ExitCode != 0)
                return new() { ["error"] = stderr.Trim() };

            return new()
            {
                ["repo"]          = repo,
                ["state"]         = state,
                ["pull_requests"] = stdout.Trim(),
            };
        }
        catch (Exception ex)
        {
            return new() { ["error"] = $"gh not found or failed: {ex.Message}" };
        }
    }
}
