// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi07 — Streaming.
//
// An OpenAI Agents SDK support agent backed by a single knowledge-base
// tool. Demonstrates StreamAsync() — yields events as the agent thinks,
// calls tools, and completes.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var agent = OpenAIAgent.Builder()
    .Name("support_agent")
    .Instructions(
        "You are a customer support agent. Use the knowledge base to answer " +
        "questions accurately. If you can't find the answer, say so honestly.")
    .Model(Settings.LlmModel)
    .Tools(new KnowledgeBaseTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });

Console.WriteLine("Streaming agent execution:");
Console.WriteLine(new string('-', 40));

await foreach (var ev in runtime.StreamAsync(agent, "What's your return policy for electronics?"))
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
            Console.WriteLine("  [waiting...]");
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

internal sealed class KnowledgeBaseTools
{
    private static readonly Dictionary<string, string> _knowledge = new()
    {
        ["return policy"] = "Returns accepted within 30 days with receipt. " +
                            "Electronics have a 15-day return window.",
        ["shipping"]      = "Free shipping on orders over $50. " +
                            "Standard delivery: 3-5 business days.",
        ["warranty"]      = "All products come with a 1-year manufacturer warranty. " +
                            "Extended warranty available for electronics.",
    };

    [Tool(Name = "search_knowledge_base", Description = "Search the knowledge base for relevant information.")]
    public string SearchKnowledgeBase(string query)
    {
        var lower = query.ToLowerInvariant();
        foreach (var (k, v) in _knowledge)
        {
            if (lower.Contains(k)) return v;
        }
        return "No relevant information found for your query.";
    }
}
