// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Wait for Message — continuously receive messages via Workflow Message Queue.
//
// Demonstrates:
//   - WaitForMessageTool: dequeues messages from the WMQ (Conductor PULL_WORKFLOW_MESSAGES task)
//   - Mixing a server-side message tool with a local action tool
//   - Looping agent that keeps processing messages indefinitely
//   - Pushing messages from outside the workflow with runtime.SendMessageAsync()
//
// The agent loops forever: each iteration waits for a message, reads the
// "task" field, executes it, and goes back to listening.
//
// Requirements:
//   - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Server-side WMQ tool (no worker needed) ────────────────────

var receiveMessage = WaitForMessageTool.Create(
    name: "wait_for_message",
    description: "Wait until a message is sent to this agent, then return its contents.");

// ── Local action tool ─────────────────────────────────────────

var executeTaskTools = ToolRegistry.FromInstance(new TaskExecutor());

// ── Agent ─────────────────────────────────────────────────────

var agent = new Agent("message_listener_75")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveMessage, .. executeTaskTools],
    Instructions =
        "You are a task-execution agent that runs forever in a loop. " +
        "Repeat this cycle indefinitely: " +
        "1. Call wait_for_message to receive the next message. " +
        "2. Extract the 'task' field from the message payload. " +
        "3. Call execute_task with that task string. " +
        "4. Go back to step 1 immediately — never stop.",
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent, "Start listening for messages.");
Console.WriteLine($"Agent started: {handle.ExecutionId}");
Console.WriteLine("Sending messages...\n");

var messages = new[] { "summarize quarterly report", "draft release notes", "check system health" };
foreach (var msg in messages)
{
    await Task.Delay(2000);
    Console.WriteLine($"  -> sending: {msg}");
    await runtime.SendMessageAsync(handle.ExecutionId, new { task = msg });
}

// Let the agent process all messages
await Task.Delay(30_000);
await handle.StopAsync();

Console.WriteLine("\nAgent stopped. Waiting for final status...");
var result = await handle.WaitAsync();
result.PrintResult();

// ── Tool class ─────────────────────────────────────────────────

internal sealed class TaskExecutor
{
    [Tool("Execute a task and return the result.")]
    public string ExecuteTask(string task)
    {
        Console.WriteLine($"\n*** EXECUTING: {task} ***\n");
        return $"Task completed: {task}";
    }
}
