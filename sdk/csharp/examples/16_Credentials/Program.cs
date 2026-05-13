// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Credentials — per-user secrets resolved from the credential store.
//
// Demonstrates [Tool(Credentials = ["GITHUB_TOKEN"])] which tells the
// server to resolve GITHUB_TOKEN from the credential store and inject
// it into the tool's execution environment before the worker runs.
//
// Setup (one-time):
//   agentspan credentials set GITHUB_TOKEN <your-token>
//
// The ToolContext.ExecutionToken carries the scoped execution token
// that the SDK uses when calling POST /api/credentials/resolve.
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment
//   - GITHUB_TOKEN stored via `agentspan credentials set`

using System.Net.Http.Headers;
using System.Text.Json;
using Agentspan;
using Agentspan.Examples;

var tools = ToolRegistry.FromInstance(new GitHubTools());

var agent = new Agent("github_agent")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a GitHub assistant. You can list repositories for a user. " +
        "Always report how many repos were found.",
    Tools = tools,
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    agent,
    "List the 5 most recently updated repos for the 'agentspan-ai' GitHub org.");

result.PrintResult();

// ── Tool class ────────────────────────────────────────────────────────

internal sealed class GitHubTools
{
    private static readonly HttpClient _http = new();

    [Tool("List public repositories for a GitHub user or org.",
          Credentials = ["GITHUB_TOKEN"])]
    public async Task<Dictionary<string, object>> ListGithubRepos(
        string username, ToolContext? ctx = null)
    {
        // In isolated mode the server injects GITHUB_TOKEN into the worker's
        // process environment before invoking the handler.
        var token = Environment.GetEnvironmentVariable("GITHUB_TOKEN") ?? "";

        var request = new HttpRequestMessage(
            HttpMethod.Get,
            $"https://api.github.com/users/{username}/repos?per_page=5&sort=updated");

        request.Headers.UserAgent.Add(new ProductInfoHeaderValue("agentspan-csharp-sdk", "0.1"));
        if (!string.IsNullOrEmpty(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);

        try
        {
            var response = await _http.SendAsync(request);
            var body     = await response.Content.ReadAsStringAsync();

            if (!response.IsSuccessStatusCode)
                return new() { ["error"] = $"GitHub API error {(int)response.StatusCode}" };

            var repos = JsonSerializer.Deserialize<JsonElement[]>(body) ?? [];
            var list  = repos.Select(r => new
            {
                name  = r.GetProperty("name").GetString(),
                stars = r.GetProperty("stargazers_count").GetInt32(),
            }).ToList();

            return new()
            {
                ["username"]      = username,
                ["repos"]         = list,
                ["authenticated"] = !string.IsNullOrEmpty(token),
            };
        }
        catch (Exception ex)
        {
            return new() { ["error"] = ex.Message };
        }
    }
}
