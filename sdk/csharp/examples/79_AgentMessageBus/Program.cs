// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Agent Message Bus — two agents communicating via Workflow Message Queue.
//
// Demonstrates:
//   - Agent-to-agent messaging: a Researcher forwards results directly into
//     a Writer agent's WMQ via runtime.SendMessageAsync()
//   - A tool that closes over an execution_id to forward results downstream
//   - Parallel agent pipelines: researcher → writer running concurrently
//   - Deterministic stop: handle.StopAsync() exits each agent's loop gracefully
//
// How this differs from 06_SequentialPipeline:
//   The >> operator in example 06 compiles a static DAG upfront. Here both
//   agents are independent running workflows. The Researcher decides at runtime
//   when and what to forward, and could conditionally route or fan out.
//
// Scenario:
//   A Researcher agent receives topics, produces bullet-point notes, then
//   forwards them to a Writer agent that turns them into a polished paragraph.
//   The main thread only sends topics to the Researcher — the Researcher
//   autonomously drives the Writer.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

const int TopicCount = 3;

// Signal main thread when all Writer paragraphs have been published
var allPublished = new SemaphoreSlim(0);

// ── Writer agent ───────────────────────────────────────────────

var receiveNotes = WaitForMessageTool.Create(
    name:        "wait_for_notes",
    description: "Wait for research notes from the Researcher. Payload: {topic, notes}.");

var writerTools = ToolRegistry.FromInstance(new WriterTools(allPublished));

var writerAgent = new Agent("writer_79")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveNotes, .. writerTools],
    Instructions =
        "You are a Writer agent. Repeat indefinitely:\n" +
        "1. Call wait_for_notes to receive the next message.\n" +
        "2. Turn the notes into a single polished paragraph (3–4 sentences).\n" +
        "3. Call publish(topic, paragraph) with the topic and your paragraph.\n" +
        "4. Return to step 1 immediately.",
};

// ── Start runtime and Writer ───────────────────────────────────

await using var runtime = new AgentRuntime();

var writerHandle = await runtime.StartAsync(writerAgent, "Begin. Wait for research notes.");
var writerId     = writerHandle.ExecutionId;
Console.WriteLine($"Writer     started: {writerId}");

// ── Researcher agent (needs writerId to forward messages) ──────

var receiveTopic = WaitForMessageTool.Create(
    name:        "wait_for_topic",
    description: "Wait for the next research topic.");

var researcherTools = ToolRegistry.FromInstance(new ResearcherTools(runtime, writerId));

var researcherAgent = new Agent("researcher_79")
{
    Model    = Settings.LlmModel,
    Stateful = true,
    MaxTurns = 10000,
    Tools    = [receiveTopic, .. researcherTools],
    Instructions =
        "You are a Researcher agent. Repeat indefinitely:\n" +
        "1. Call wait_for_topic to receive the next message.\n" +
        "2. Write three concise bullet-point research notes on the topic.\n" +
        "3. Call forward_to_writer(topic, notes) with the topic and your notes.\n" +
        "4. Return to step 1 immediately.",
};

var researcherHandle = await runtime.StartAsync(researcherAgent, "Begin. Wait for your first topic.");
var researcherId     = researcherHandle.ExecutionId;
Console.WriteLine($"Researcher started: {researcherId}\n");

// ── Send topics ────────────────────────────────────────────────

var topics = new[]
{
    "the impact of edge computing on cloud infrastructure",
    "why Rust is gaining adoption in systems programming",
    "how vector databases work",
};

await Task.Delay(3_000);  // Let agents reach their first wait call

Console.WriteLine("Sending topics to Researcher...\n");
foreach (var topic in topics)
{
    Console.WriteLine($"  -> {topic}");
    await runtime.SendMessageAsync(researcherId, new { topic });
}

// ── Wait for writer to publish all paragraphs, then stop ───────

Console.WriteLine($"\nWaiting for {TopicCount} paragraphs to be published...\n");
for (int i = 0; i < TopicCount; i++)
    await allPublished.WaitAsync();

Console.WriteLine("\nAll paragraphs published. Stopping agents...");
await researcherHandle.StopAsync();
await writerHandle.StopAsync();

await researcherHandle.WaitAsync();
await writerHandle.WaitAsync();

Console.WriteLine("Done.");

// ── Tool classes ───────────────────────────────────────────────

internal sealed class ResearcherTools(AgentRuntime runtime, string writerId)
{
    [Tool("Forward research notes to the Writer agent.")]
    public async Task<string> ForwardToWriter(string topic, string notes)
    {
        Console.WriteLine($"  [researcher -> writer] forwarding notes on '{topic}'");
        await runtime.SendMessageAsync(writerId, new { topic, notes });
        return "forwarded";
    }
}

internal sealed class WriterTools(SemaphoreSlim published)
{
    [Tool("Publish the finished paragraph for a topic.")]
    public string Publish(string topic, string paragraph)
    {
        Console.WriteLine($"\n  [writer] -- {topic} --");
        Console.WriteLine($"  {paragraph}\n");
        published.Release();
        return "published";
    }
}
