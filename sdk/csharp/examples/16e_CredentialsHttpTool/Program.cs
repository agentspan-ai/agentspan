// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Credentials — HTTP tool with server-side credential resolution.
//
// Demonstrates:
//   - HttpTools.Create() with credentials: ["GITHUB_TOKEN"]
//   - ${GITHUB_TOKEN} in headers resolved server-side (not in C#)
//   - No worker process needed — Conductor makes the HTTP call directly
//
// The ${NAME} syntax in headers tells the server to substitute the
// credential value from the store at execution time. The plaintext
// value never appears in the workflow definition.
//
// Setup (one-time):
//   agentspan credentials set GITHUB_TOKEN <your-github-token>
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - GITHUB_TOKEN stored via `agentspan credentials set`

using Agentspan;
using Agentspan.Examples;

// HTTP tool with credential-bearing headers.
// ${GITHUB_TOKEN} is resolved server-side from the credential store.
var listRepos = HttpTools.Create(
    name:        "list_github_repos",
    description: "List public GitHub repositories for a user. Returns JSON with name, url, and stars.",
    url:         "https://api.github.com/users/agentspan-ai/repos?per_page=5&sort=updated",
    headers:     new Dictionary<string, string>
    {
        ["Authorization"]        = "Bearer ${GITHUB_TOKEN}",
        ["Accept"]               = "application/vnd.github.v3+json",
        ["X-GitHub-Api-Version"] = "2022-11-28",
        ["User-Agent"]           = "agentspan-sdk",
    },
    credentials: ["GITHUB_TOKEN"]);

var agent = new Agent("github_http_agent_16e")
{
    Model        = Settings.LlmModel,
    Tools        = [listRepos],
    Instructions =
        "You list GitHub repos using the list_github_repos tool. " +
        "Summarize the most recently updated ones.",
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "List the repos for agentspan-ai");
result.PrintResult();
