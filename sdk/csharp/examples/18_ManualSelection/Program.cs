// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Manual Selection — human picks which agent speaks next.
//
// Strategy.Manual pauses execution each turn to let a human
// select which agent should respond next via AgentHandle.RespondAsync().
//
//   editorial_team (MANUAL)
//   ├── writer
//   ├── editor
//   └── fact_checker
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Editorial team agents ─────────────────────────────────────────────

var writer = new Agent("writer")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a creative writer. Expand on ideas with vivid prose.",
};

var editor = new Agent("editor")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a strict editor. Improve clarity, fix issues, tighten prose.",
};

var factChecker = new Agent("fact_checker")
{
    Model        = Settings.LlmModel,
    Instructions = "You verify claims and flag anything inaccurate or unsupported.",
};

// Manual strategy: human picks which agent speaks each turn
var team = new Agent("editorial_team")
{
    Model    = Settings.LlmModel,
    Agents   = [writer, editor, factChecker],
    Strategy = Strategy.Manual,
    MaxTurns = 3,
};

// ── Run with automated selections (simulates human input) ─────────────

await using var runtime = new AgentRuntime();
var handle = await runtime.StartAsync(
    team,
    "Write a short paragraph about the history of artificial intelligence.");

Console.WriteLine($"Started: {handle.ExecutionId}\n");

// Simulate human selections: writer → editor → fact_checker
var selections = new[] { "writer", "editor", "fact_checker" };
var selectionIndex = 0;

await foreach (var ev in handle.StreamAsync())
{
    switch (ev.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {ev.Content}");
            break;

        case EventType.ToolCall:
            Console.WriteLine($"  [tool_call] {ev.ToolName}");
            break;

        case EventType.Waiting:
            // Human picks the next agent
            var selected = selectionIndex < selections.Length
                ? selections[selectionIndex++]
                : "writer";

            Console.WriteLine($"\n--- Selecting agent: {selected} ---\n");
            await handle.RespondAsync(new { selected });
            break;

        case EventType.Done:
            Console.WriteLine($"\nDone: {ev.Content}");
            break;

        case EventType.Error:
            Console.WriteLine($"\nError: {ev.Content}");
            break;
    }
}

var result = await handle.WaitAsync();
result.PrintResult();
