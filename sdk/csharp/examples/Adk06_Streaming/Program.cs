// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk06 — Streaming.
//
// A documentation lookup ADK agent. Demonstrates StreamAsync() — yields
// events as the agent thinks, calls tools, and completes.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("docs_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a documentation assistant. Use the search tool to find " +
        "relevant docs and provide clear, well-formatted answers.")
    .Tools(new DocsTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });

Console.WriteLine("Streaming agent execution:");
Console.WriteLine(new string('-', 40));

await foreach (var ev in runtime.StreamAsync(agent, "How do I authenticate with the API?"))
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
        case EventType.Done:
            Console.WriteLine();
            Console.WriteLine($"Result: {ev.Content}");
            break;
        case EventType.Error:
            Console.WriteLine($"  [error] {ev.Content}");
            break;
    }
}

internal sealed class DocsTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _docs = new()
    {
        ["installation"] = new()
        {
            ["title"]   = "Installation Guide",
            ["content"] = "Run `pip install mypackage`. Requires Python 3.9+.",
        },
        ["authentication"] = new()
        {
            ["title"]   = "Authentication",
            ["content"] = "Use API keys via the X-API-Key header. Keys are managed in the dashboard.",
        },
        ["rate limits"] = new()
        {
            ["title"]   = "Rate Limiting",
            ["content"] = "Free tier: 100 req/min. Pro: 1000 req/min. Enterprise: unlimited.",
        },
    };

    [Tool(Name = "search_documentation", Description = "Search the product documentation.")]
    public Dictionary<string, object> SearchDocumentation(string query)
    {
        var lower = query.ToLowerInvariant();
        foreach (var (k, v) in _docs)
        {
            if (lower.Contains(k))
            {
                var r = new Dictionary<string, object> { ["found"] = true };
                foreach (var (kk, vv) in v) r[kk] = vv;
                return r;
            }
        }
        return new Dictionary<string, object> { ["found"] = false, ["message"] = "No matching documentation found." };
    }
}
