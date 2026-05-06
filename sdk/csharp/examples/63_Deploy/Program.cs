// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Deploy — register agents on the server (CI/CD step).
//
// Demonstrates:
//   - runtime.DeployAsync() to compile and register multiple agents
//   - DeploymentInfo result with agent name and registered workflow name
//   - CI/CD use case: push agent definitions without executing them
//
// DeployAsync() sends agent configs to the server which compiles them into
// Conductor workflow definitions and registers task definitions. No local
// workers are started and no execution happens.
//
// In production, run this once during CI/CD:
//   dotnet run --project 63_Deploy  # registers agent definitions
//
// Then run the worker service separately (see 63b_Serve) to keep workers alive.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Agent definitions ───────────────────────────────────────────

var docAssistant = new Agent("doc_assistant_63")
{
    Model        = Settings.LlmModel,
    Instructions = "Help users find documentation. Use search_docs to look up answers.",
    Tools        = ToolRegistry.FromInstance(new DocTools()),
};

var opsBot = new Agent("ops_bot_63")
{
    Model        = Settings.LlmModel,
    Instructions = "Monitor service health. Use check_status to inspect services.",
    Tools        = ToolRegistry.FromInstance(new OpsTools()),
};

// ── Deploy (no workers, no execution) ──────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("Deploying agents...\n");
var results = await runtime.DeployAsync(docAssistant, opsBot);

foreach (var info in results)
    Console.WriteLine($"  Deployed: {info.AgentName} -> {info.RegisteredName}");

Console.WriteLine("\nAgents deployed. Run 63b_Serve to start worker processes.");
Console.WriteLine("Run 63c_RunByName to execute without local workers.");

// ── Tool classes ─────────────────────────────────────────────

internal sealed class DocTools
{
    [Tool("Search internal documentation.")]
    public string SearchDocs(string query)
        => $"Found 3 results for: {query}";
}

internal sealed class OpsTools
{
    [Tool("Check service health status.")]
    public string CheckStatus(string service)
        => $"{service}: healthy";
}
