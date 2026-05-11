// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Plan (Dry Run) — compile an agent without executing it.
//
// Demonstrates:
//   - runtime.PlanAsync() to compile an agent to a Conductor workflow
//   - Inspecting the compiled workflow structure (tasks, loops, tool routing)
//   - CI/CD validation: verify agents compile correctly before deployment
//
// PlanAsync() sends the agent config to the server, which compiles it into
// a Conductor WorkflowDef and returns it — without registering, starting
// workers, or executing.
//
// Requirements:
//   - Agentspan server running
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using System.Text.Json.Nodes;
using Agentspan;
using Agentspan.Examples;

// ── Define the agent (same as any other example) ──────────────

var agent = new Agent("research_writer_57")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a research writer. Research topics and write reports.",
    Tools        = ToolRegistry.FromInstance(new ResearchWriterTools()),
    MaxTurns     = 10,
};

// ── Plan: compile without executing ───────────────────────────

await using var runtime = new AgentRuntime();
var planResult = await runtime.PlanAsync(agent);

if (planResult is null)
{
    Console.WriteLine("Plan returned no result.");
    return;
}

var workflowDef = planResult["workflowDef"];
if (workflowDef is not null)
{
    Console.WriteLine($"Workflow name: {workflowDef["name"]}");
    var tasks = workflowDef["tasks"]?.AsArray();
    Console.WriteLine($"Total tasks:   {tasks?.Count ?? 0}");
    Console.WriteLine();

    if (tasks is not null)
    {
        foreach (var task in tasks)
        {
            var type    = task?["type"]?.GetValue<string>() ?? "?";
            var refName = task?["taskReferenceName"]?.GetValue<string>() ?? "?";
            Console.WriteLine($"  [{type}] {refName}");

            if (type == "DO_WHILE")
            {
                var loopOver = task?["loopOver"]?.AsArray();
                if (loopOver is not null)
                {
                    foreach (var sub in loopOver)
                    {
                        var subType    = sub?["type"]?.GetValue<string>() ?? "?";
                        var subRefName = sub?["taskReferenceName"]?.GetValue<string>() ?? "?";
                        Console.WriteLine($"    [{subType}] {subRefName}");
                    }
                }
            }
        }
    }
}

Console.WriteLine("\n--- Required Workers ---");
var requiredWorkers = planResult["requiredWorkers"]?.AsArray();
if (requiredWorkers is not null)
{
    foreach (var worker in requiredWorkers)
        Console.WriteLine($"  - {worker}");
}
else
{
    Console.WriteLine("  (none)");
}

// ── Tool class ────────────────────────────────────────────────

internal sealed class ResearchWriterTools
{
    [Tool("Search the web for information.")]
    public Dictionary<string, object> SearchWeb(string query)
        => new() { ["query"] = query, ["results"] = new List<string> { "result1", "result2" } };

    [Tool("Write a section of a report.")]
    public Dictionary<string, object> WriteReport(string title, string content)
        => new() { ["section"] = $"## {title}\n\n{content}" };
}
