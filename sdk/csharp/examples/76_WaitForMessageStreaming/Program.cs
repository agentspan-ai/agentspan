// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Wait for Message (Streaming) — send messages to a running agent and stream its responses.
//
// Demonstrates:
//   - WaitForMessageTool with streaming: push messages in and see the agent react
//   - Using handle.StreamAsync() to observe WAITING → processing → WAITING cycles
//   - runtime.SendMessageAsync() to push payloads into the Workflow Message Queue
//
// The agent starts, immediately waits for a message, processes whatever it
// receives (by calling wait_for_message again), then waits again. The caller
// drives the conversation by sending messages and reading streamed events.
//
// Requirements:
//   - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Tools ─────────────────────────────────────────────────────

var receiveMessage = WaitForMessageTool.Create(
    name: "wait_for_message",
    description:
        "Wait for the next instruction from the caller. " +
        "The message payload contains a 'task' field with the request.");

var respondTools = ToolRegistry.FromInstance(new Responder());

// ── Agent ─────────────────────────────────────────────────────

var agent = new Agent("reactive_agent_76")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveMessage, .. respondTools],
    Instructions =
        "You are a reactive agent. Repeat this cycle indefinitely without stopping: " +
        "1. Call wait_for_message to receive your next instruction. " +
        "2. Think through the task in the 'task' field and formulate a complete answer. " +
        "3. Call respond() with your full answer. " +
        "4. Go back to step 1 immediately — never stop.",
};

// ── Run ───────────────────────────────────────────────────────

string[] tasks =
[
    "List three benefits of microservices architecture",
    "Suggest a name for a new AI productivity app",
    "Write a one-line C# expression that reverses a string",
];

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent, "Begin. Wait for your first instruction.");
Console.WriteLine($"Agent started: {handle.ExecutionId}\n");

// Push messages from a background task while streaming events on the main task.
var cts = new CancellationTokenSource();

_ = Task.Run(async () =>
{
    foreach (var task in tasks)
    {
        await Task.Delay(8000);
        Console.WriteLine($"\n  [caller] sending -> {task}");
        await runtime.SendMessageAsync(handle.ExecutionId, new { task });
    }
    await handle.StopAsync();
});

// Stream events until the agent terminates
await foreach (var evt in handle.StreamAsync())
{
    switch (evt.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {evt.Content}");
            break;

        case EventType.ToolCall when evt.ToolName == "respond":
            Console.WriteLine($"  [tool_call] respond");
            break;

        case EventType.Waiting:
            Console.WriteLine($"  [waiting] agent is waiting for next message");
            break;

        case EventType.Error:
            Console.WriteLine($"  [error] {evt.Content}");
            break;

        case EventType.Done:
            Console.WriteLine($"\nAgent finished: {evt.Status}");
            goto done;
    }
}
done:;

// ── Tool class ─────────────────────────────────────────────────

internal sealed class Responder
{
    [Tool("Send your answer back to the caller.")]
    public string Respond(string answer)
    {
        Console.WriteLine($"  [answer] {answer}");
        return "ok";
    }
}
