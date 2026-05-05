// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Live Dashboard — a Feeder agent streams metrics into a Monitor agent in real time.
//
// Demonstrates:
//   - WMQ batch_size: Monitor dequeues up to 10 metric samples per LLM turn
//   - Two concurrently running stateful agents coordinated via WMQ
//   - In-process IPC using Channel<string> and SemaphoreSlim
//     (vs Python's filesystem IPC, since C# workers run in-process)
//
// How it works:
//   1. Monitor starts; its execution_id is captured in a variable shared
//      with the Feeder tool closure (in-process — no file needed).
//   2. The main thread sends batch signals to the Feeder's WMQ.
//   3. The Feeder dequeues each signal, generates 5 random metric samples
//      and pushes them directly into the Monitor's WMQ.
//   4. The Monitor wakes up, pulls up to 10 samples at once, computes
//      min/max/avg per metric, and calls display_dashboard with a summary.
//   5. display_dashboard writes to an in-process Channel<string> so the
//      main thread can print summaries as they arrive.
//   6. After all expected summaries are received, both agents are stopped.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment
//   - Conductor server with WMQ support (conductor.workflow-message-queue.enabled=true)

using System.Threading.Channels;
using Agentspan;
using Agentspan.Examples;

const int TotalBatches      = 6;
const int SamplesPerBatch   = 5;
const int MonitorBatchSize  = 10;
const int TotalSamples      = TotalBatches * SamplesPerBatch;
int ExpectedDisplays        = (int)Math.Ceiling((double)TotalSamples / MonitorBatchSize);

// ── In-process coordination (replaces Python's filesystem IPC) ─────────
var dashboardChannel = Channel.CreateUnbounded<string>();
var batchesDispatched = new SemaphoreSlim(0);
string? monitorId = null;  // set after Monitor starts; read by FeederTools

await using var runtime = new AgentRuntime();

// ── Monitor agent ──────────────────────────────────────────────────────

var monitor = new Agent("monitor_agent_80")
{
    Model    = Settings.LlmModel,
    MaxTurns = 10000,
    Stateful = true,
    Tools    =
    [
        WaitForMessageTool.Create(
            name:        "receive_metrics",
            description: "Dequeue the next batch of up to 10 metric samples. "
                       + "Each sample has 'metric', 'host', and 'value' fields.",
            batchSize:   MonitorBatchSize),
        ToolDefFactory.Create(
            name:        "display_dashboard",
            description: "Publish an aggregated dashboard summary line for this batch.",
            handler:     (args, _) =>
            {
                var summary = args.TryGetValue("summary", out var s) ? s.GetString() ?? "" : "";
                dashboardChannel.Writer.TryWrite(summary);
                return Task.FromResult<object?>("displayed");
            },
            inputSchema: new System.Text.Json.Nodes.JsonObject
            {
                ["type"] = "object",
                ["properties"] = new System.Text.Json.Nodes.JsonObject
                {
                    ["summary"] = new System.Text.Json.Nodes.JsonObject
                    {
                        ["type"] = "string",
                        ["description"] = "Compact one-line summary of this batch's stats.",
                    },
                },
                ["required"] = new System.Text.Json.Nodes.JsonArray { "summary" },
            }),
    ],
    Instructions =
        "You are a real-time metrics monitor. Repeat indefinitely:\n"
      + "1. Call receive_metrics — you get a batch of 1–10 metric samples.\n"
      + "2. Compute per-metric statistics: count, min, max, average value.\n"
      + "3. Call display_dashboard with a compact one-line summary like:\n"
      + "   'Batch 3 | cpu_pct: n=4 min=12.1 max=87.3 avg=45.2 | mem_mb: n=3 …'\n"
      + "4. Return to step 1 immediately.",
};

// ── Feeder agent ───────────────────────────────────────────────────────

var rng = new Random();
string[] MetricNames = ["cpu_pct", "mem_mb", "req_rate", "latency_ms", "error_rate"];
string[] Hosts       = ["web-01", "web-02", "db-01"];

var feeder = new Agent("feeder_agent_80")
{
    Model    = Settings.LlmModel,
    MaxTurns = 10000,
    Stateful = true,
    Tools    =
    [
        WaitForMessageTool.Create(
            name:        "receive_signal",
            description: "Wait for a control signal from the orchestrator ({batches: N})."),
        ToolDefFactory.Create(
            name:        "push_metrics_batch",
            description: "Generate and push one batch of metric samples to the Monitor agent.",
            handler:     async (args, _) =>
            {
                var batchNumber = args.TryGetValue("batch_number", out var bn) ? bn.GetInt32() : 0;
                var mid = monitorId!;  // set before agents are started

                var samples = new List<object>();
                for (var i = 0; i < SamplesPerBatch; i++)
                {
                    var metric = MetricNames[rng.Next(MetricNames.Length)];
                    var host   = Hosts[rng.Next(Hosts.Length)];
                    var value  = Math.Round(rng.NextDouble() * 100, 2);
                    var sample = new { metric, host, value };
                    samples.Add(sample);
                    await runtime.SendMessageAsync(mid, sample);
                }

                batchesDispatched.Release();
                return (object?)$"Pushed {samples.Count} samples in batch {batchNumber}.";
            },
            inputSchema: new System.Text.Json.Nodes.JsonObject
            {
                ["type"] = "object",
                ["properties"] = new System.Text.Json.Nodes.JsonObject
                {
                    ["batch_number"] = new System.Text.Json.Nodes.JsonObject
                    {
                        ["type"] = "integer",
                        ["description"] = "Sequential batch number (1-based).",
                    },
                },
                ["required"] = new System.Text.Json.Nodes.JsonArray { "batch_number" },
            }),
    ],
    Instructions =
        "You are a metrics Feeder agent. Repeat indefinitely:\n"
      + "1. Call receive_signal to get the next instruction.\n"
      + "2. If the signal contains 'batches: N', call push_metrics_batch N times "
      +    "(once per batch, incrementing batch_number from 1 to N).\n"
      + "3. Return to step 1 immediately.",
};

// ── Start agents ────────────────────────────────────────────────────────

Console.WriteLine("Starting Monitor agent...");
var monitorHandle = await runtime.StartAsync(monitor, "Begin. Wait for metric batches.");
monitorId = monitorHandle.ExecutionId;
Console.WriteLine($"Monitor  started: {monitorId}");

Console.WriteLine("Starting Feeder agent...");
var feederHandle = await runtime.StartAsync(feeder, "Begin. Wait for orchestrator signals.");
Console.WriteLine($"Feeder   started: {feederHandle.ExecutionId}\n");

// Give agents time to reach their first WMQ wait.
await Task.Delay(4000);

// ── Send batch signals to Feeder ────────────────────────────────────────

Console.WriteLine($"Sending {TotalBatches} batch signals to Feeder "
                + $"({SamplesPerBatch} metrics each = {TotalSamples} total samples, "
                + $"Monitor reads ≤{MonitorBatchSize} per call)...\n");

int firstHalf = TotalBatches / 2;
int secondHalf = TotalBatches - firstHalf;
await runtime.SendMessageAsync(feederHandle.ExecutionId, new { batches = firstHalf });
await runtime.SendMessageAsync(feederHandle.ExecutionId, new { batches = secondHalf });

// ── Wait for all batches to be dispatched ──────────────────────────────

Console.WriteLine("Waiting for all batches to be dispatched...");
for (var i = 0; i < TotalBatches; i++)
    await batchesDispatched.WaitAsync();
Console.WriteLine($"  All {TotalBatches} batches dispatched ({TotalSamples} samples in Monitor's queue).\n");

// ── Print dashboard summaries as they arrive ───────────────────────────

Console.WriteLine($"Live dashboard (Monitor processes ≤{MonitorBatchSize} samples per batch):\n");

var displayCount = 0;
using var dashCts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
while (displayCount < ExpectedDisplays)
{
    string summary;
    try
    {
        summary = await dashboardChannel.Reader.ReadAsync(dashCts.Token);
    }
    catch (OperationCanceledException)
    {
        Console.WriteLine("(Timed out waiting for dashboard summaries.)");
        break;
    }
    displayCount++;
    Console.WriteLine($"  [dashboard batch {displayCount}] {summary}");
}

Console.WriteLine($"\nAll {displayCount} batch reports received. Stopping...\n");

feederHandle.Stop();
monitorHandle.Stop();

Console.WriteLine("Done.");
