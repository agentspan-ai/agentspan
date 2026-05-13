// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Kafka Consumer Agent — forward Kafka records into a running agent via WMQ.
//
// Demonstrates:
//   - WaitForMessageTool: agent blocks until a message arrives in its WMQ
//   - A background Kafka consumer loop that forwards each record to the
//     agent via runtime.SendMessageAsync()
//   - Stateful, long-running agent that processes an unbounded stream
//
// Agent loop (runs forever):
//   1. wait_for_message() — dequeue the next WMQ payload (pushed by Kafka)
//   2. echo_message()     — print the record to the console
//   3. Back to step 1
//
// Requirements:
//   - Agentspan server running at http://localhost:6767
//   - Kafka broker on localhost:9092 with topic "agentspan_topic"
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Confluent.Kafka;
using Agentspan;
using Agentspan.Examples;

const string KafkaBootstrap = "localhost:9092";
const string KafkaTopic     = "agentspan_topic";
const string KafkaGroup     = "agentspan-echo-group";

// ── Tools ─────────────────────────────────────────────────────

var waitForMessage = WaitForMessageTool.Create(
    name:        "wait_for_message",
    description: "Wait for the next Kafka record forwarded to this agent. " +
                 "Payload: {value, topic, partition, offset}.");

var echoTool = ToolDefFactory.Create(
    name:        "echo_message",
    description: "Echo a received Kafka record to the console.",
    handler: (args, _) =>
    {
        var value     = args.TryGetValue("value",     out var v) ? v.GetString() ?? "" : "";
        var topic     = args.TryGetValue("topic",     out var t) ? t.GetString() ?? "" : "";
        var offset    = args.TryGetValue("offset",    out var o) ? o.GetInt64() : 0;
        var line      = $"[{topic}@{offset}] {value}";
        Console.WriteLine($"  {line}");
        return Task.FromResult<object?>(line);
    },
    inputSchema: new System.Text.Json.Nodes.JsonObject
    {
        ["type"]       = "object",
        ["properties"] = new System.Text.Json.Nodes.JsonObject
        {
            ["value"]     = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
            ["topic"]     = new System.Text.Json.Nodes.JsonObject { ["type"] = "string" },
            ["partition"] = new System.Text.Json.Nodes.JsonObject { ["type"] = "integer" },
            ["offset"]    = new System.Text.Json.Nodes.JsonObject { ["type"] = "integer" },
        },
        ["required"] = new System.Text.Json.Nodes.JsonArray { "value", "topic", "offset" },
    });

// ── Agent ─────────────────────────────────────────────────────

var kafkaAgent = new Agent("kafka_echo_agent_77")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 100_000,
    Tools    = [waitForMessage, echoTool],
    Instructions =
        "You are a Kafka consumer agent that runs forever. " +
        "Repeat this cycle indefinitely without stopping:\n" +
        "1. Call wait_for_message to receive the next Kafka record.\n" +
        "2. Call echo_message with the value, topic, partition, and offset from the payload.\n" +
        "3. Go back to step 1 immediately.",
};

// ── Start agent ───────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var handle = await runtime.StartAsync(kafkaAgent, "Start consuming messages from Kafka.");
Console.WriteLine($"Agent started: {handle.ExecutionId}");
Console.WriteLine($"Consuming from topic '{KafkaTopic}' on {KafkaBootstrap}...");
Console.WriteLine("Press Ctrl+C to stop.\n");

// ── Kafka consumer loop ───────────────────────────────────────

using var cts      = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

var config = new ConsumerConfig
{
    BootstrapServers = KafkaBootstrap,
    GroupId          = KafkaGroup,
    AutoOffsetReset  = AutoOffsetReset.Latest,
};

using var consumer = new ConsumerBuilder<Ignore, string>(config).Build();
consumer.Subscribe(KafkaTopic);

try
{
    while (!cts.Token.IsCancellationRequested)
    {
        var msg = consumer.Consume(cts.Token);
        if (msg?.Message is null) continue;

        Console.WriteLine($"  [kafka] received: {msg.Message.Value}");
        await runtime.SendMessageAsync(handle.ExecutionId, new
        {
            value     = msg.Message.Value,
            topic     = msg.Topic,
            partition = msg.Partition.Value,
            offset    = msg.Offset.Value,
        });
    }
}
catch (OperationCanceledException) { }
finally
{
    consumer.Close();
}

// ── Stop agent ────────────────────────────────────────────────

Console.WriteLine("\nStopping agent...");
await handle.StopAsync();
await handle.WaitAsync();
Console.WriteLine("Done.");
