// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Approval Workflow — agent dynamically decides which tasks need human sign-off.
//
// Demonstrates:
//   - WaitForMessageTool as a dynamic approval gate driven by LLM reasoning
//   - The agent itself decides mid-loop whether a task is risky, rather than
//     the workflow having a fixed approval step baked in
//   - flag_for_approval blocks the tool worker until the main thread responds
//     via TaskCompletionSource — no second wait needed for the decision
//   - In-process synchronization: C# workers run in the same process, so
//     Channel<T> and TaskCompletionSource replace filesystem IPC
//   - Deterministic stop: handle.StopAsync() exits the loop gracefully
//
// How this differs from examples 09a–09d (HITL):
//   In 09a–09d the approval pause is baked into the workflow definition at
//   compile time — always pauses at that point regardless of input.
//   Here the LLM inspects each task and decides dynamically: safe tasks flow
//   through immediately, risky ones block pending human sign-off.
//
// Scenario:
//   An ops agent processes system commands. Safe commands (reads, status) run
//   immediately. Destructive commands (deletes, restarts, permission changes)
//   block pending approval. Type Y to approve or N to reject.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Threading.Channels;
using Agentspan;
using Agentspan.Examples;

// ── In-process synchronization ─────────────────────────────────

// Tool workers write to this channel; main thread reads and responds
var approvalChannel = Channel.CreateUnbounded<ApprovalRequest>();

// Released by execute_task and log_rejection each time a task completes
var tasksDone = new SemaphoreSlim(0);

// ── Agent tools ────────────────────────────────────────────────

var receiveMessage = WaitForMessageTool.Create(
    name:        "wait_for_message",
    description: "Dequeue the next task or stop signal ({stop: true}).");

var opsTools = ToolRegistry.FromInstance(new OpsTools(approvalChannel.Writer, tasksDone));

// ── Agent ───────────────────────────────────────────────────────

var agent = new Agent("approval_agent_78")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveMessage, .. opsTools],
    Instructions =
        "You are an operations agent that processes system commands with a safety gate. " +
        "Repeat this cycle indefinitely:\n\n" +
        "1. Call wait_for_message to receive the next message.\n" +
        "2. Assess the task:\n" +
        "   - SAFE (status checks, reads, listing): call execute_task immediately.\n" +
        "   - RISKY (deletes, restarts, permission changes, writes): call flag_for_approval " +
        "     with the task and a brief reason. It will block until the operator decides " +
        "     and return 'approve' or 'reject'.\n" +
        "3. If flag_for_approval returned 'approve', call execute_task. " +
        "   If it returned 'reject', call log_rejection.\n" +
        "4. Return to step 1 immediately.",
};

// ── Tasks ───────────────────────────────────────────────────────

var tasks = new[]
{
    "List all running services",
    "Delete all logs older than 7 days",
    "Check disk usage on /var",
    "Restart the payment-service pod",
    "Grant admin access to user@example.com",
};

// ── Run ─────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

var handle = await runtime.StartAsync(agent, "Start processing the task queue.");
Console.WriteLine($"Agent started: {handle.ExecutionId}\n");

await Task.Delay(3_000);  // Let agent reach its first wait call

Console.WriteLine("Dispatching all tasks...\n");
foreach (var task in tasks)
{
    Console.WriteLine($"  -> '{task}'");
    await runtime.SendMessageAsync(handle.ExecutionId, new { task });
}
Console.WriteLine();

// Poll for approval requests; respond when the operator decides.
// Poll for completions to know when to stop.
int completedCount = 0;
while (completedCount < tasks.Length)
{
    // Check for pending approval requests (non-blocking)
    while (approvalChannel.Reader.TryRead(out var req))
    {
        Console.WriteLine($"\n  ⚠ APPROVAL REQUIRED");
        Console.WriteLine($"    Task:   {req.Task}");
        Console.WriteLine($"    Reason: {req.Reason}");
        Console.Write("  Approve? [Y/N]: ");
        var answer = (Console.ReadLine() ?? "N").Trim().ToUpper() == "Y" ? "approve" : "reject";
        req.Decision.SetResult(answer);
    }

    // Count completed tasks (non-blocking)
    while (tasksDone.Wait(0))
        completedCount++;

    if (completedCount < tasks.Length)
        await Task.Delay(100);
}

Console.WriteLine();
// Deterministic stop — no stop-handling instructions needed.
await handle.StopAsync();
await handle.WaitAsync();
Console.WriteLine("\nDone.");

// ── Tool classes ─────────────────────────────────────────────

record ApprovalRequest(string Task, string Reason, TaskCompletionSource<string> Decision);

internal sealed class OpsTools(
    ChannelWriter<ApprovalRequest> approvals,
    SemaphoreSlim done)
{
    [Tool("Execute a safe, pre-approved task immediately.")]
    public string ExecuteTask(string task)
    {
        Console.WriteLine($"\n  ✓ EXECUTING: {task}\n");
        done.Release();
        return $"Completed: {task}";
    }

    [Tool("Request operator approval. Blocks until the operator decides. Returns 'approve' or 'reject'.")]
    public async Task<string> FlagForApproval(string task, string reason)
    {
        var tcs = new TaskCompletionSource<string>();
        await approvals.WriteAsync(new ApprovalRequest(task, reason, tcs));
        return await tcs.Task;  // blocks until main thread responds
    }

    [Tool("Log a task that was rejected by the operator.")]
    public string LogRejection(string task)
    {
        Console.WriteLine($"\n  ✗ REJECTED: {task}\n");
        done.Release();
        return $"Rejected: {task}";
    }
}
