// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Serve — keep tool workers running as a persistent service.
//
// Demonstrates:
//   - runtime.ServeAsync() to register C# workers and block until Ctrl+C
//   - Serving multiple agents in a single process
//   - Decoupled from deploy: workers only, no workflow registration
//
// ServeAsync() registers the C# tool methods as Conductor workers and
// starts polling for tasks. The workflow must already exist on the server
// (from a prior DeployAsync() or RunAsync() call, possibly in a different
// process).
//
// Start this in a long-running process and press Ctrl+C to stop:
//   dotnet run --project 63b_Serve
//
// Requirements:
//   - Agents already deployed (run 63_Deploy first)
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Agent definitions (same as in 63_Deploy) ───────────────────

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

// ── Serve workers until Ctrl+C ─────────────────────────────────

Console.WriteLine("Worker service starting. Press Ctrl+C to stop.\n");
Console.WriteLine("Workers polling for tasks:");
Console.WriteLine("  - search_docs (doc_assistant_63)");
Console.WriteLine("  - check_status (ops_bot_63)\n");

using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    Console.WriteLine("\nShutting down...");
    cts.Cancel();
};

await using var runtime = new AgentRuntime();
await runtime.ServeAsync(cts.Token, docAssistant, opsBot);

Console.WriteLine("Worker service stopped.");

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
