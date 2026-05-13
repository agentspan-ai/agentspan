// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Serve from Assembly — auto-discover and serve all agents in an assembly.
//
// Demonstrates:
//   - DiscoverAgents(assembly) — reflection-based auto-discovery
//   - Scanning the current assembly for agent provider classes
//   - Deploying and serving all discovered agents in a single call
//
// DiscoverAgents() finds all public static properties and fields of type Agent
// across all types in the assembly, then returns them as a flat list. This
// mirrors Python's discover_agents(packages=[...]) which scans module-level
// Agent instances.
//
//   dotnet run --project 63d_ServeFromAssembly
//
// Requirements:
//   - Agentspan server running at AGENTSPAN_SERVER_URL
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Reflection;
using Agentspan;
using Agentspan.Examples;

// ── Agent definitions (in AgentLibrary below) ─────────────────────────
//
// In a real project these would live in separate files (e.g. Agents/Monitoring.cs).
// Here they are static properties on AgentLibrary for simplicity.

// ── Discover ──────────────────────────────────────────────────────────

var discovered = DiscoverAgents(Assembly.GetExecutingAssembly());
Console.WriteLine($"Discovered {discovered.Count} agent(s):");
foreach (var a in discovered)
    Console.WriteLine($"  - {a.Name}");
Console.WriteLine();

// ── Run one of the discovered agents ──────────────────────────────────

await using var runtime = new AgentRuntime();

var result = await runtime.RunAsync(
    AgentLibrary.MonitoringAgent,
    "Is everything healthy? Run a full check.");
result.PrintResult();

// ── Serve all discovered agents (blocks until Ctrl+C) ─────────────────
//
// Uncomment for production use:
//
// using var cts = new CancellationTokenSource();
// Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
// Console.WriteLine("Worker service started. Press Ctrl+C to stop.");
// await runtime.ServeAsync(cts.Token, [.. discovered]);

// ── Discovery helper ──────────────────────────────────────────────────

static List<Agent> DiscoverAgents(Assembly assembly)
{
    var agents = new List<Agent>();

    foreach (var type in assembly.GetTypes())
    {
        // Static properties of type Agent
        foreach (var prop in type.GetProperties(BindingFlags.Public | BindingFlags.Static))
        {
            if (prop.PropertyType == typeof(Agent) && prop.GetValue(null) is Agent a)
                agents.Add(a);
        }

        // Static fields of type Agent
        foreach (var field in type.GetFields(BindingFlags.Public | BindingFlags.Static))
        {
            if (field.FieldType == typeof(Agent) && field.GetValue(null) is Agent a)
                agents.Add(a);
        }
    }

    return agents;
}

// ── Agent library ─────────────────────────────────────────────────────
// These agents are discovered automatically by DiscoverAgents().

internal static class AgentLibrary
{
    public static Agent MonitoringAgent { get; } = new Agent("monitoring_63d")
    {
        Model        = Settings.LlmModel,
        Tools        = ToolRegistry.FromInstance(new HealthCheckTools()),
        Instructions = "You monitor system health. Use health_check to inspect services.",
    };

    public static Agent ReportAgent { get; } = new Agent("reporter_63d")
    {
        Model        = Settings.LlmModel,
        Instructions = "You generate status reports from data you receive.",
    };
}

// ── Tool class ─────────────────────────────────────────────────────────

internal sealed class HealthCheckTools
{
    [Tool("Perform a basic health check. Returns health status.")]
    public string HealthCheck(string service = "all") =>
        service == "all"
            ? "All systems operational: api=OK db=OK cache=OK"
            : $"{service}: OK";
}
