// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Worker Service Recovery — workflow waits durably while workers are down.
//
// Demonstrates:
//   - Deploying an agent separately from running its worker service
//   - Starting a workflow by name while no worker service is running
//   - Watching the same workflow complete after the worker service starts
//
// This proves worker-service durability. The workflow remains stored on the
// Agentspan/Conductor server while .NET tool workers are unavailable. When
// a worker service comes back online, the server dispatches the stalled task
// and the workflow continues to completion.
//
// The example runs in two phases within one process:
//   Phase 1 — Deploy + start by name (no workers). Workflow queues on the server.
//   Phase 2 — Worker service starts. Stalled tasks are dispatched. Workflow completes.
//
// In production you'd split these into separate processes:
//   CI/CD :  runtime.DeployAsync(agent)
//   Worker:  runtime.ServeAsync(ct, agent)   [long-lived service]
//   Client:  runtime.StartByNameAsync(name, prompt)
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("worker_restart_recovery_73")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a release validation assistant. When asked to validate "
                 + "a change, call simulate_release_validation exactly once, then "
                 + "report whether it passed.",
    Tools        = ToolRegistry.FromInstance(new ValidationTools()),
};

await using var runtime = new AgentRuntime();

// ── Phase 1: Deploy + start by name (no workers) ─────────────────────

Console.WriteLine("=== Phase 1: Deploy ===");
var deployResults = await runtime.DeployAsync(agent);
foreach (var info in deployResults)
    Console.WriteLine($"  Deployed: {info.AgentName} -> {info.RegisteredName}");

Console.WriteLine("\nStarting workflow by name (no worker service yet)...");
var handle = await runtime.StartByNameAsync(
    agent.Name,
    "Validate change CHG-901 for production release.");

Console.WriteLine($"Execution ID: {handle.ExecutionId}");
Console.WriteLine("Workflow is queued on the server — tool tasks pending.");
Console.WriteLine("(In production the worker service would be in a separate process.)\n");

// Show the workflow is stuck waiting for workers.
await Task.Delay(3000);
var earlyStatus = await runtime.GetStatusAsync(handle.ExecutionId);
Console.WriteLine($"Status after 3s: {earlyStatus.StatusValue} (no workers to pick up tasks)");
Console.WriteLine();

// ── Phase 2: Worker service restarts ─────────────────────────────────

Console.WriteLine("=== Phase 2: Worker Service Restart ===");
Console.WriteLine("Starting worker service — workers now polling for tasks...\n");

using var cts = new CancellationTokenSource();

// ServeAsync registers workers and blocks. Run it in the background
// so we can await WaitAsync() for the completion signal.
var serveTask = runtime.ServeAsync(cts.Token, agent);

// Poll until the workflow completes.
for (var i = 0; i < 120; i++)
{
    await Task.Delay(1000);
    var s = await runtime.GetStatusAsync(handle.ExecutionId);
    Console.WriteLine($"  [{i + 1:D2}s] status={s.StatusValue}");
    if (s.IsComplete)
    {
        Console.WriteLine("\nWorkflow completed after worker service came online.\n");
        break;
    }
}

// Stop the worker service.
cts.Cancel();
try { await serveTask; } catch (OperationCanceledException) { }

// Fetch and display the final result.
var result = await handle.WaitAsync();
result.PrintResult();

// ── Tool class ────────────────────────────────────────────────────────

internal sealed class ValidationTools
{
    [Tool("Run a release validation step for a production change.")]
    public async Task<Dictionary<string, object>> SimulateReleaseValidation(string changeId)
    {
        Console.WriteLine($"  [worker] Validating {changeId}...");
        await Task.Delay(2000);  // simulate I/O-bound work
        Console.WriteLine($"  [worker] Validation complete for {changeId}.");
        return new()
        {
            ["change_id"] = changeId,
            ["status"]    = "validated",
        };
    }
}
