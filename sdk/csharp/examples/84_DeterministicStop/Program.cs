// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Deterministic Stop — exit an agent loop without LLM cooperation.
//
// Demonstrates:
//   - handle.StopAsync(): graceful, deterministic loop exit via workflow variable
//   - No stop-handling instructions needed in the agent's prompt
//   - Execution reaches COMPLETED status with last output preserved
//   - Works with both blocking and non-blocking WMQ agents
//
// How it works:
//   The server compiles every agent's DoWhile loop with a _stop_requested
//   workflow variable in its condition. When handle.StopAsync() is called, the
//   SDK signals the server to set this variable to true. The loop condition
//   evaluates to false on the next check, and the loop exits. The LLM cannot
//   override this — it's checked by Conductor, not the LLM.
//
//   For blocking WMQ agents, StopAsync() also sends a {"_signal": "stop"}
//   WMQ message to unblock the PULL_WORKFLOW_MESSAGES task.
//
// stop() vs cancel():
//   - StopAsync()  → graceful, current iteration finishes, status=COMPLETED
//   - CancelAsync() → immediate, workflow killed, status=TERMINATED
//
// Requirements:
//   - Agentspan server with _stop_requested support in compiler
//   - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Tools ─────────────────────────────────────────────────────

var receiveTask = WaitForMessageTool.Create(
    name: "wait_for_task",
    description: "Wait for the next task to process.");

var processTools = ToolRegistry.FromInstance(new TaskProcessor());

// ── Agent (NO stop-handling instructions!) ────────────────────

var agent = new Agent("stoppable_agent_84")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveTask, .. processTools],
    Instructions =
        "You are a task processor. Loop forever: " +
        "1. Call wait_for_task to receive the next task. " +
        "2. Call process_task with the task. " +
        "3. Go back to step 1.",
};

// ── Run ───────────────────────────────────────────────────────

string[] tasks = ["analyze server logs", "generate weekly report", "send status summary to team"];

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent, "Begin processing tasks.");
Console.WriteLine($"Agent started: {handle.ExecutionId}\n");

// Wait for agent to reach its first wait_for_task call
await Task.Delay(3000);

// Send tasks one by one
foreach (var task in tasks)
{
    Console.WriteLine($"  -> sending: {task}");
    await runtime.SendMessageAsync(handle.ExecutionId, new { task });
    await Task.Delay(6000);
}

// Deterministic stop — no instructions, no LLM cooperation needed
Console.WriteLine("\nSending stop signal (deterministic)...");
await handle.StopAsync();

// Wait for the agent to complete gracefully
var result = await handle.WaitAsync();
Console.WriteLine($"\nStatus: {result.Status}");  // COMPLETED (not TERMINATED)
result.PrintResult();
Console.WriteLine("Done.");

// ── Tool class ─────────────────────────────────────────────────

internal sealed class TaskProcessor
{
    [Tool("Process a task and return the result.")]
    public string ProcessTask(string task)
    {
        Console.WriteLine($"  [processing] {task}");
        return $"Completed: {task}";
    }
}
