// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Long-Running Agent — fire-and-forget with status polling.
//
// Demonstrates starting an agent asynchronously and polling its status
// from the same (or a separate) process. The agent runs as a Conductor
// workflow and can be monitored via the API or UI.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("saas_analyst")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a data analyst. Provide a brief analysis " +
        "when asked about data topics.",
};

await using var runtime = new AgentRuntime();

// ── Fire-and-forget: start the agent and get a handle immediately ──────

var handle = await runtime.StartAsync(
    agent,
    "What are the key metrics to track for a SaaS product?");

Console.WriteLine($"Agent started: {handle.ExecutionId}");
Console.WriteLine("Polling for completion...\n");

// ── Poll status until complete ────────────────────────────────────────

for (int i = 0; i < 60; i++)
{
    var status = await handle.GetStatusAsync();
    Console.WriteLine($"  [{i * 2}s] Status: {status.StatusValue ?? "?"} | Complete: {status.IsComplete}");

    if (status.IsComplete)
    {
        Console.WriteLine();
        var result = await handle.WaitAsync();
        result.PrintResult();
        return;
    }

    await Task.Delay(2000);
}

Console.WriteLine("\nAgent still running. Check the Conductor UI:");
Console.WriteLine($"  http://localhost:6767/execution/{handle.ExecutionId}");
