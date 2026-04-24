// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Client Reconnect — hard-kill the SDK process and resume later.
//
// Demonstrates:
//   - Starting a workflow and saving its execution ID to disk
//   - Workflow reaching a durable WAITING state on the server
//   - Re-attaching with a fresh AgentRuntime via ResumeAsync()
//   - Approving the HITL step and completing from the new runtime
//
// This proves client-process durability. The local .NET process can die,
// but the workflow state remains stored on the Agentspan/Conductor server.
// Workers re-register under the original domain — the workflow continues
// as if nothing happened.
//
// Run to see the full reconnect cycle in one process:
//   dotnet run --project 72_ClientReconnect
//
// In production, you'd typically split this into two binaries:
//   1. Start process — saves execution ID then crashes/exits
//   2. Resume process — reads execution ID, calls ResumeAsync(), approves
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

const string ExecutionFile = "/tmp/agentspan_client_reconnect_72.execution_id";

var agent = new Agent("client_reconnect_demo_72")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a careful release coordinator. When asked whether to "
                 + "ship a change, you must call approve_release first. After "
                 + "approval, confirm the release is approved and ready to ship.",
    Tools        = ToolRegistry.FromInstance(new ReleaseTools()),
};

// ── Phase 1: Start the workflow ───────────────────────────────────────

Console.WriteLine("=== Phase 1: Start ===");
await using var runtime1 = new AgentRuntime();

var handle1 = await runtime1.StartAsync(
    agent,
    "Ship change CHG-204: rotate the production API gateway certificates.");

File.WriteAllText(ExecutionFile, handle1.ExecutionId);
Console.WriteLine($"Execution ID : {handle1.ExecutionId}");
Console.WriteLine($"Saved to     : {ExecutionFile}");
Console.WriteLine();

// ── Poll until WAITING (approval gate reached) ────────────────────────

Console.WriteLine("Waiting for workflow to reach a durable WAITING state...");
for (var i = 0; i < 90; i++)
{
    await Task.Delay(1000);
    var s = await runtime1.GetStatusAsync(handle1.ExecutionId);
    Console.WriteLine($"  [{i + 1:D2}s] status={s.StatusValue,-12} waiting={s.IsWaiting}");

    if (s.IsWaiting)
    {
        Console.WriteLine("\nWorkflow is durably paused — approval gate reached.");
        Console.WriteLine("(In production the original process would crash here.)");
        break;
    }
    if (s.IsComplete)
    {
        Console.WriteLine("\nWorkflow completed before reaching approval gate.");
        return;
    }
}

// Dispose the first runtime (workers shut down — simulates the process dying).
await runtime1.DisposeAsync();
Console.WriteLine("\nFirst runtime disposed. Workers are gone.\n");

// ── Phase 2: Reconnect with a fresh runtime ───────────────────────────

Console.WriteLine("=== Phase 2: Reconnect ===");
var savedId = File.ReadAllText(ExecutionFile).Trim();
Console.WriteLine($"Read execution ID from disk: {savedId}");

await using var runtime2 = new AgentRuntime();

// ResumeAsync fetches the workflow from the server, extracts the worker
// domain from taskToDomain, and re-registers tool workers under that domain.
var handle2 = await runtime2.ResumeAsync(savedId, agent);
Console.WriteLine($"Re-attached to execution   : {handle2.ExecutionId}");
Console.WriteLine();

// ── Approve and complete ──────────────────────────────────────────────

Console.WriteLine("Sending approval...");
await runtime2.RespondAsync(savedId, new { approved = true });

Console.WriteLine("Waiting for completion...\n");
var result = await handle2.WaitAsync();
result.PrintResult();

// ── Tool class ────────────────────────────────────────────────────────

internal sealed class ReleaseTools
{
    [Tool("Approve a production release change after human review.",
          ApprovalRequired = true)]
    public Dictionary<string, object> ApproveRelease(string changeId)
        => new() { ["change_id"] = changeId, ["approved"] = true };
}
