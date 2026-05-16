// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Credentials — External worker credential resolution.
//
// Demonstrates:
//   - External tool declared as a ToolDef with External = true and
//     Credentials = ["GITHUB_TOKEN"]. In C#, external tools must be
//     created as ToolDef objects directly (unlike local tools which use
//     [Tool] attributes and ToolRegistry.FromInstance).
//   - The external worker calls AgentHttpClient.ResolveCredentialsAsync()
//     to fetch the plaintext credential value at runtime.
//   - Works for workers running in separate processes, containers, or machines.
//
// Two sides are shown:
//   1. Agent definition (declares the external tool with credentials)
//   2. External worker pattern (shown in comments; runs in a separate process)
//
// Setup (one-time):
//   agentspan credentials set GITHUB_TOKEN <your-github-token>
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment
//   - GITHUB_TOKEN stored via `agentspan credentials set`
//   - An external worker polling for "github_lookup" tasks (see comments below)

using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.Examples;

// ── External tool declaration ─────────────────────────────────
//
// External tools are created as ToolDef objects with External = true.
// They have no local handler — execution dispatches to an external
// Conductor worker process.

var githubLookup = new ToolDef
{
    Name        = "github_lookup",
    Description = "Look up a GitHub user's public profile. Runs on an external worker.",
    External    = true,
    Credentials = ["GITHUB_TOKEN"],
    InputSchema = new JsonObject
    {
        ["type"]       = "object",
        ["properties"] = new JsonObject
        {
            ["username"] = new JsonObject
            {
                ["type"]        = "string",
                ["description"] = "The GitHub username to look up.",
            },
        },
        ["required"] = new JsonArray { "username" },
    },
};

// ── Agent side: declare external tool with credentials ──────────

var agent = new Agent("external_cred_agent_16h")
{
    Model        = Settings.LlmModel,
    Tools        = [githubLookup],
    Instructions =
        "You can look up GitHub users. Use the github_lookup tool. " +
        "GITHUB_TOKEN is automatically resolved by the external worker.",
};

// ── Run ───────────────────────────────────────────────────────

Console.WriteLine("=== External Worker Credentials ===");
Console.WriteLine("The agent declares the external tool; a separate worker handles execution.");
Console.WriteLine("The worker resolves GITHUB_TOKEN from the server at runtime.\n");
Console.WriteLine("Note: This example requires an external worker to be running.");
Console.WriteLine("See the comment block below for the worker implementation pattern.\n");

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Look up the GitHub profile for torvalds.");
result.PrintResult();

/*
 * ── External worker side (runs in a separate process) ─────────────────
 *
 * The external worker polls Conductor for tasks named "github_lookup".
 * It uses AgentHttpClient.ResolveCredentialsAsync() to fetch the
 * GITHUB_TOKEN value from the Agentspan server at runtime.
 *
 * Implementation sketch:
 *
 *   using Agentspan;
 *   using OrchestratorSDK.Client;           // Conductor .NET SDK
 *   using System.Net.Http.Headers;
 *   using System.Text.Json;
 *
 *   var serverUrl = Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL")!;
 *   var http = new AgentHttpClient(serverUrl);
 *   var taskClient = new TaskResourceApi(new Configuration { BasePath = serverUrl });
 *
 *   while (true)
 *   {
 *       var task = await taskClient.PollAsync("github_lookup", workerId: "worker-1");
 *       if (task is null) { await Task.Delay(1000); continue; }
 *
 *       // Extract the execution token injected by Agentspan into __agentspan_ctx__
 *       string? executionToken = null;
 *       if (task.InputData.TryGetValue("__agentspan_ctx__", out var ctxRaw))
 *       {
 *           var ctx = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
 *               ctxRaw.ToString()!);
 *           if (ctx?.TryGetValue("execution_token", out var tok) == true)
 *               executionToken = tok.GetString();
 *       }
 *
 *       // Resolve GITHUB_TOKEN from the server using the execution token
 *       var creds = await http.ResolveCredentialsAsync(executionToken, ["GITHUB_TOKEN"]);
 *       var token = creds.GetValueOrDefault("GITHUB_TOKEN", "");
 *
 *       // Use the credential to call the GitHub API
 *       var username = task.InputData["username"].ToString();
 *       using var ghClient = new HttpClient();
 *       ghClient.DefaultRequestHeaders.Authorization =
 *           new AuthenticationHeaderValue("Bearer", token);
 *       ghClient.DefaultRequestHeaders.Add("User-Agent", "agentspan-worker");
 *
 *       var resp = await ghClient.GetAsync($"https://api.github.com/users/{username}");
 *       // ... complete the Conductor task with the response data
 *   }
 */
