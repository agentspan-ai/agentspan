// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Fan-Out / Fan-In — orchestrator broadcasts tasks to workers, collector aggregates.
//
// Demonstrates:
//   - Fan-out: Orchestrator receives a question and sends it to N Worker agents
//     by calling runtime.SendMessageAsync once per worker
//   - Fan-in: each Worker sends its answer into the Collector agent's WMQ
//   - Four concurrently running workflows: Orchestrator + 3 Workers + Collector
//   - Unique tool names per worker: Conductor routes tasks by definition name,
//     so workers sharing a name would race each other's tasks.
//     Use ToolDefFactory.Create() to build tools with dynamic names.
//   - In-process synchronization: SemaphoreSlim tracks published reports
//
// Scenario:
//   A research Orchestrator fans out each question to three Worker agents
//   (alpha, beta, gamma) that produce independent short answers.
//   The Collector aggregates the three answers into a side-by-side report.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using Agentspan;
using Agentspan.Examples;

const int NumWorkers = 3;
string[] WorkerNames = ["alpha", "beta", "gamma"];

string[] Questions =
[
    "What are the main trade-offs between microservices and monolithic architectures?",
    "How does a transformer model differ from a recurrent neural network?",
    "What problem does consistent hashing solve in distributed systems?",
];

// Signal main thread when all reports are saved (NumQuestions reports)
var reportsDone = new SemaphoreSlim(0);
// Captured reports for display
var reports = new System.Collections.Concurrent.ConcurrentDictionary<string, string>();

await using var runtime = new AgentRuntime();

// ── Collector agent ────────────────────────────────────────────
// Fan-in: receives results from all workers, aggregates into reports.

var receiveResult = WaitForMessageTool.Create(
    name:        "receive_result",
    description: "Wait for the next worker result. Payload: {question, worker_name, answer}.");

var saveReportTool = ToolDefFactory.Create(
    name:        "save_report",
    description: "Save the aggregated side-by-side report.",
    handler: (args, _) =>
    {
        var question = args.TryGetValue("question", out var q) ? q.GetString() ?? "" : "";
        var report   = args.TryGetValue("report",   out var r) ? r.GetString() ?? "" : "";
        reports[question] = report;
        reportsDone.Release();
        Console.WriteLine($"\n  [report saved for: {question[..Math.Min(50, question.Length)]}...]");
        return Task.FromResult<object?>("saved");
    },
    inputSchema: new System.Text.Json.Nodes.JsonObject
    {
        ["type"] = "object",
        ["properties"] = new System.Text.Json.Nodes.JsonObject
        {
            ["question"] = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
            ["report"]   = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
        },
        ["required"] = new System.Text.Json.Nodes.JsonArray { "question", "report" },
    });

var collectorAgent = new Agent("collector_82")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveResult, saveReportTool],
    Instructions =
        $"You are a Collector agent. You receive individual worker answers and aggregate them. " +
        $"There are always {NumWorkers} workers ({string.Join(", ", WorkerNames)}) answering each question.\n\n" +
        "Repeat indefinitely:\n" +
        $"1. Call receive_result {NumWorkers} times to collect all answers for one question " +
        "   (they share the same 'question' field).\n" +
        "2. Build a side-by-side comparison: for each worker list their name and a one-sentence summary.\n" +
        "3. Call save_report(question, report) with the formatted report string.\n" +
        "4. Return to step 1.",
};

var collectorHandle = await runtime.StartAsync(collectorAgent, "Begin. Wait for worker results.");
var collectorId     = collectorHandle.ExecutionId;
Console.WriteLine($"Collector    started: {collectorId}");

// ── Worker agents ──────────────────────────────────────────────
// Each worker has unique tool names to avoid Conductor task routing collisions.

var workerHandles = new List<AgentHandle>();

foreach (var workerName in WorkerNames)
{
    var name = workerName;  // capture for closure

    var receiveTask = WaitForMessageTool.Create(
        name:        $"receive_task_{name}",
        description: $"Wait for the next task for worker {name}. Payload: {{question}}.");

    var submitAnswerTool = ToolDefFactory.Create(
        name:        $"submit_answer_{name}",
        description: "Send this worker's answer to the Collector.",
        handler: async (args, _) =>
        {
            var question   = args.TryGetValue("question",    out var q) ? q.GetString() ?? "" : "";
            var answer     = args.TryGetValue("answer",      out var a) ? a.GetString() ?? "" : "";

            await runtime.SendMessageAsync(collectorId, new { question, worker_name = name, answer });
            Console.WriteLine($"  [worker {name}] submitted answer for: {question[..Math.Min(40, question.Length)]}...");
            return (object?)"submitted";
        },
        inputSchema: new System.Text.Json.Nodes.JsonObject
        {
            ["type"] = "object",
            ["properties"] = new System.Text.Json.Nodes.JsonObject
            {
                ["question"] = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
                ["answer"]   = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
            },
            ["required"] = new System.Text.Json.Nodes.JsonArray { "question", "answer" },
        });

    var workerAgent = new Agent($"worker_{name}_82")
    {
        Model    = Settings.LlmModel,
        Stateful = true,
        MaxTurns = 10000,
        Tools    = [receiveTask, submitAnswerTool],
        Instructions =
            $"You are Worker {name.ToUpper()}, one of {NumWorkers} parallel analysts. " +
            "Repeat indefinitely:\n" +
            $"1. Call receive_task_{name} to get the next assignment.\n" +
            "2. Write a concise 2–3 sentence answer to the question.\n" +
            $"3. Call submit_answer_{name}(question, answer).\n" +
            "4. Return to step 1 immediately.",
    };

    var wh = await runtime.StartAsync(workerAgent, $"Begin. You are worker {name.ToUpper()}. Wait for tasks.");
    workerHandles.Add(wh);
    Console.WriteLine($"Worker {name,-5}  started: {wh.ExecutionId}");
}

// ── Orchestrator agent ─────────────────────────────────────────

var workerIds = workerHandles.Select(h => h.ExecutionId).ToArray();

var receiveQuestion = WaitForMessageTool.Create(
    name:        "receive_question",
    description: "Wait for the next question to fan out.");

var fanOutTool = ToolDefFactory.Create(
    name:        "fan_out",
    description: "Broadcast the question to all worker agents simultaneously.",
    handler: async (args, _) =>
    {
        var question = args.TryGetValue("question", out var q) ? q.GetString() ?? "" : "";
        foreach (var wid in workerIds)
            await runtime.SendMessageAsync(wid, new { question });
        Console.WriteLine($"  [orchestrator] fanned out: {question[..Math.Min(50, question.Length)]}...");
        return (object?)$"broadcasted to {workerIds.Length} workers";
    },
    inputSchema: new System.Text.Json.Nodes.JsonObject
    {
        ["type"] = "object",
        ["properties"] = new System.Text.Json.Nodes.JsonObject
        {
            ["question"] = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
        },
        ["required"] = new System.Text.Json.Nodes.JsonArray { "question" },
    });

var orchestratorAgent = new Agent("orchestrator_82")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveQuestion, fanOutTool],
    Instructions =
        "You are an Orchestrator agent. Repeat indefinitely:\n" +
        "1. Call receive_question to get the next question.\n" +
        "2. Call fan_out(question) to broadcast to all workers.\n" +
        "3. Return to step 1 immediately.",
};

var orchestratorHandle = await runtime.StartAsync(orchestratorAgent, "Begin. Wait for questions to fan out.");
Console.WriteLine($"Orchestrator started: {orchestratorHandle.ExecutionId}\n");

// ── Send questions ─────────────────────────────────────────────

await Task.Delay(4_000);  // Let agents reach their first wait call

Console.WriteLine($"Fanning out {Questions.Length} questions to {NumWorkers} workers...\n");
foreach (var q in Questions)
{
    Console.WriteLine($"  -> {q[..Math.Min(60, q.Length)]}...");
    await runtime.SendMessageAsync(orchestratorHandle.ExecutionId, new { question = q });
}

// ── Wait for all reports ───────────────────────────────────────

Console.WriteLine($"\nWaiting for {Questions.Length} aggregated reports...\n");
for (int i = 0; i < Questions.Length; i++)
    await reportsDone.WaitAsync();

// ── Print reports ──────────────────────────────────────────────

Console.WriteLine("\n" + new string('═', 60));
foreach (var (question, report) in reports)
{
    Console.WriteLine($"\nQuestion: {question}");
    Console.WriteLine(new string('-', 60));
    Console.WriteLine(report);
}

// ── Stop all agents ────────────────────────────────────────────

Console.WriteLine("\n" + new string('═', 60));
Console.WriteLine("\nStopping all agents...");
await orchestratorHandle.StopAsync();
foreach (var wh in workerHandles) await wh.StopAsync();
await collectorHandle.StopAsync();

await orchestratorHandle.WaitAsync();
foreach (var wh in workerHandles) await wh.WaitAsync();
await collectorHandle.WaitAsync();

Console.WriteLine("Done.");
