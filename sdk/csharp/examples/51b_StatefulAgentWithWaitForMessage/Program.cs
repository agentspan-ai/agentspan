// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Stateful Agent with WaitForMessage — a long-running agent that waits for external messages.
//
// Demonstrates:
//   - Agent.Stateful = true: enables domain-based routing so all worker tasks
//     (tools, callbacks, termination) execute on the same worker process.
//   - WaitForMessageTool: dequeues messages from the Workflow Message Queue.
//   - Mixing a server-side WMQ tool with local action tools in a stateful agent.
//   - Using runtime.StartAsync() + runtime.SendMessageAsync() for external control.
//
// Pattern (mirrors Python 51_shared_state.py and 75_WaitForMessage.py):
//   1. Create a stateful agent with WaitForMessageTool + a local action tool.
//   2. Start the agent in the background with StartAsync().
//   3. Send external messages with runtime.SendMessageAsync().
//   4. Stop the agent with handle.StopAsync().
//
// Requirements:
//   - Agentspan server with Workflow Message Queue support
//     (conductor.workflow-message-queue.enabled=true)
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Server-side WMQ tool (no worker needed) ─────────────────────────────────

var receiveMessage = WaitForMessageTool.Create(
    name:        "wait_for_message",
    description: "Wait until an external message is sent to this agent, then return its content.");

// ── Local action tool ────────────────────────────────────────────────────────

var actionTools = ToolRegistry.FromInstance(new StatefulActionTools());

// ── Agent ────────────────────────────────────────────────────────────────────
//
// Stateful = true enables domain-based routing: all tool calls during this
// execution are pinned to the same worker process instance. This is required
// when using WaitForMessageTool in combination with local worker tools, so the
// worker that is waiting for messages is the same one that receives them.

var agent = new Agent("stateful_message_listener_51b")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveMessage, .. actionTools],
    Instructions =
        "You are a stateful message-processing agent. " +
        "Repeat this cycle indefinitely until instructed to stop:\n" +
        "1. Call wait_for_message to receive the next external message.\n" +
        "2. Extract the 'action' field from the message.\n" +
        "3. Call process_action with that action string and report the result.\n" +
        "4. Return to step 1 immediately.",
};

// ── Run ──────────────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent, "Start listening for external messages.");
Console.WriteLine($"Stateful agent started. ExecutionId: {handle.ExecutionId}");
Console.WriteLine();

// Send a few external messages — the agent processes them one at a time
var actions = new[] { "generate-report", "check-health", "summarize-logs" };

foreach (var action in actions)
{
    await Task.Delay(2000);
    Console.WriteLine($"  -> Sending action: {action}");
    await runtime.SendMessageAsync(handle.ExecutionId, new { action });
}

// Give the agent time to process all messages before stopping
Console.WriteLine();
Console.WriteLine("Waiting for agent to process messages...");
await Task.Delay(20_000);

Console.WriteLine("Stopping agent...");
await handle.StopAsync();

var result = await handle.WaitAsync();
result.PrintResult();

// ── Tool class ───────────────────────────────────────────────────────────────

/// <summary>
/// Local action tools for the stateful agent.
/// Because the agent has Stateful=true, these tools are pinned to the same
/// worker process for the lifetime of the execution (domain-based routing).
/// </summary>
internal sealed class StatefulActionTools
{
    private int _processedCount;

    [Tool("Process an action and return a deterministic result. " +
          "Increments the per-execution counter each time it is called.")]
    public Dictionary<string, object> ProcessAction(string action)
    {
        _processedCount++;
        Console.WriteLine($"\n*** PROCESSING ACTION #{_processedCount}: {action} ***\n");

        return new Dictionary<string, object>
        {
            ["action"]    = action,
            ["result"]    = $"Action '{action}' completed successfully.",
            ["callCount"] = _processedCount,
        };
    }

    [Tool("Return a status summary of all actions processed in this execution.")]
    public Dictionary<string, object> GetStatus()
        => new()
        {
            ["totalProcessed"] = _processedCount,
            ["status"]         = _processedCount > 0 ? "active" : "idle",
        };
}
