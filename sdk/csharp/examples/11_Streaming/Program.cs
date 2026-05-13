// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Streaming — real-time event stream from an agent execution.
//
// Demonstrates StreamAsync() which yields AgentEvent objects as the
// agent thinks, calls tools, and completes.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("haiku_writer")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a haiku poet. Write a single haiku.",
};

Console.WriteLine("Streaming agent execution:");
Console.WriteLine(new string('-', 40));

await using var runtime = new AgentRuntime();

await foreach (var ev in runtime.StreamAsync(agent, "Write a haiku about C# programming."))
{
    switch (ev.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {ev.Content}");
            break;
        case EventType.ToolCall:
            Console.WriteLine($"  [tool_call] {ev.ToolName}");
            break;
        case EventType.ToolResult:
            Console.WriteLine($"  [tool_result] {ev.ToolName}");
            break;
        case EventType.Waiting:
            Console.WriteLine("  [waiting...]");
            break;
        case EventType.Done:
            Console.WriteLine();
            Console.WriteLine($"Result: {ev.Content}");
            Console.WriteLine($"Status: {ev.Status}");
            break;
        case EventType.Error:
            Console.WriteLine($"  [error] {ev.Content}");
            break;
    }
}
