// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Run Monitoring — trigger a deployed agent by name from a separate process.
//
// Demonstrates:
//   - runtime.RunByNameAsync(name, prompt) — running an agent without an Agent object
//   - The deploy/serve/run separation in practice
//
// This is the companion to 63d_ServeFromAssembly:
//   Terminal 1: dotnet run --project 63d_ServeFromAssembly  (deploys + runs workers)
//   Terminal 2: dotnet run --project 63e_RunMonitoring       (triggers the agent by name)
//
// RunByNameAsync() assumes the workflow is already registered on the server.
// It dispatches by workflow name — no Agent object or tool registration needed
// in this process.
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - monitoring_63d agent previously deployed (run 63d first)

using Agentspan;

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Run Monitoring Agent by Name ---");
Console.WriteLine("Triggering 'monitoring_63d' workflow on the server...\n");

var result = await runtime.RunByNameAsync(
    "monitoring_63d",
    "Is everything healthy? Run a full check.");

result.PrintResult();
