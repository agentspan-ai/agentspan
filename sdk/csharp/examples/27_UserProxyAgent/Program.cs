// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// UserProxyAgent — human stand-in for interactive conversations.
//
// UserProxyAgent.Create() builds an Agent with metadata that tells the
// server to pause when it's the proxy's turn and await human input via
// AgentHandle.RespondAsync.
//
// Modes:
//   Always    — always pause for human input (this example)
//   Terminate — pause only when the conversation would end
//   Never     — auto-respond, useful for testing
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Human proxy ───────────────────────────────────────────────────────

var human = UserProxyAgent.Create(name: "human", humanInputMode: HumanInputMode.Always);

// ── AI coding assistant ───────────────────────────────────────────────

var assistant = new Agent("assistant")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a helpful coding assistant. Help the user write Python code. " +
        "Ask clarifying questions when needed.",
};

// ── Round-robin: human and assistant take turns (2 exchanges) ─────────

var conversation = new Agent("pair_programming")
{
    Model    = Settings.LlmModel,
    Agents   = [human, assistant],
    Strategy = Strategy.RoundRobin,
    MaxTurns = 4,   // human, assistant, human, assistant
};

// ── Run with streaming — respond when the proxy waits ────────────────

await using var runtime = new AgentRuntime();
var handle = await runtime.StartAsync(
    conversation,
    "Let's write a Python function to sort a list of dictionaries by a key.");

Console.WriteLine($"Started: {handle.ExecutionId}\n");

await foreach (var ev in handle.StreamAsync())
{
    switch (ev.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {ev.Content}");
            break;

        case EventType.ToolCall:
            Console.WriteLine($"  [tool_call] {ev.ToolName}({ev.Args})");
            break;

        case EventType.ToolResult:
            Console.WriteLine($"  [tool_result] {ev.ToolName} -> {ev.Result}");
            break;

        case EventType.Waiting:
            Console.Write("\n--- Human input required: ");
            var userInput = Console.ReadLine()?.Trim() ?? "Continue.";
            await handle.RespondAsync(new { human_input = userInput });
            Console.WriteLine();
            break;

        case EventType.Done:
            Console.WriteLine($"\nDone: {ev.Content ?? ev.Status}");
            break;

        case EventType.Error:
            Console.WriteLine($"\nError: {ev.Content}");
            break;
    }
}
