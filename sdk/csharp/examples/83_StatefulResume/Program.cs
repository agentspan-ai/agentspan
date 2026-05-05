// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Stateful Agent Resume — reconnect to a running workflow after runtime restart.
//
// Demonstrates:
//   - Starting a stateful agent with WaitForMessageTool
//   - Closing the runtime (workers die, workflow persists on server)
//   - Resuming with runtime.ResumeAsync() — domain automatically extracted
//     from the server's taskToDomain mapping, no RunId needed
//   - Workers re-register under the original domain, workflow continues
//
// How this works:
//   Phase 1: Start the agent, send a task, let it process, then close the
//   runtime. Workers die but the workflow is durable on the server — it
//   stays in RUNNING state, waiting for a message.
//
//   Phase 2: Create a fresh AgentRuntime and call ResumeAsync(). It fetches
//   the workflow from the server, reads taskToDomain to discover the domain
//   UUID, and re-registers workers under that domain. The server dispatches
//   stalled tasks to the new workers and the agent picks up where it left off.
//
// Requirements:
//   - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

const string SessionFile = "/tmp/agentspan_stateful_resume_83.session";

var agent = new Agent("resumable_agent_83")
{
    Model       = Settings.LlmModel,
    Tools       = [
        WaitForMessageTool.Create(
            name:        "wait_for_message",
            description: "Wait until a message is sent to this agent, then return its contents."),
        .. ToolRegistry.FromInstance(new TaskTools()),
    ],
    MaxTurns    = 10000,
    Stateful    = true,
    Instructions =
        "You are a task-execution agent that runs forever in a loop. " +
        "Repeat this cycle indefinitely: " +
        "1. Call wait_for_message to receive the next message. " +
        "2. If the message contains 'stop: true', respond with 'Stopping.' " +
        "   and call no further tools. " +
        "3. Otherwise extract the 'task' field and call execute_task with it. " +
        "4. Go back to step 1 immediately.",
};

// ── Phase 1: Start, send a task, then close runtime ─────────────────────

Console.WriteLine(new string('=', 60));
Console.WriteLine("Phase 1: Start agent, send a task, then close runtime");
Console.WriteLine(new string('=', 60));

string executionId;

await using (var runtime1 = new AgentRuntime())
{
    var handle = await runtime1.StartAsync(agent, "Start listening for messages.");
    executionId = handle.ExecutionId;
    Console.WriteLine($"\nAgent started: {executionId}");
    Console.WriteLine($"RunId (domain): {handle.RunId ?? "(none — stateful domain assigned by server)"}");

    // Save for Phase 2
    await File.WriteAllTextAsync(SessionFile, executionId);
    Console.WriteLine($"Saved execution ID to {SessionFile}");

    // Give the agent time to reach its first wait call
    await Task.Delay(3000);
    Console.WriteLine("\nSending task: 'summarize quarterly report'");
    await runtime1.SendMessageAsync(executionId, new { task = "summarize quarterly report" });
    await Task.Delay(8000);
}

Console.WriteLine("\nRuntime closed — workers are dead, workflow persists on server.\n");

// ── Phase 2: Resume with a fresh runtime ─────────────────────────────────

Console.WriteLine(new string('=', 60));
Console.WriteLine("Phase 2: Resume with a fresh runtime");
Console.WriteLine(new string('=', 60));

var savedId = (await File.ReadAllTextAsync(SessionFile)).Trim();
Console.WriteLine($"\nResuming execution: {savedId}");

await using var runtime2 = new AgentRuntime();
var resumed = await runtime2.ResumeAsync(savedId, agent);
Console.WriteLine($"Resumed! RunId (domain): {resumed.RunId}");

// Give the re-registered workers time to connect
await Task.Delay(3000);
Console.WriteLine("\nSending task: 'check system health'");
await runtime2.SendMessageAsync(savedId, new { task = "check system health" });
await Task.Delay(8000);

// Clean shutdown
Console.WriteLine("\nSending stop signal...");
await runtime2.SendMessageAsync(savedId, new { stop = true });
await resumed.WaitAsync();
Console.WriteLine("\nDone — same workflow, same domain, seamless resume.");

// ── Tool class ─────────────────────────────────────────────────

internal sealed class TaskTools
{
    [Tool("Execute a task and return the result.")]
    public string ExecuteTask(string task)
    {
        Console.WriteLine($"\n  ✓ EXECUTING: {task}\n");
        return $"Task completed: {task}";
    }
}
