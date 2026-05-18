// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk08 — Instruction Templating.
//
// ADK's instruction templating with {variable} syntax. Variables are
// resolved from session state at runtime by the server.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("adaptive_tutor")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a personalized programming tutor. " +
        "The current user is {user_name} with {expertise_level} expertise. " +
        "Adapt your explanations to their level. " +
        "Use the search_tutorials tool to find appropriate learning resources.")
    .Tools(new PrefTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent, "I want to learn Python. What tutorials do you recommend?");
result.PrintResult();

internal sealed class PrefTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _users = new()
    {
        ["user_001"] = new()
        {
            ["name"]             = "Alice",
            ["language"]         = "English",
            ["expertise"]        = "beginner",
            ["preferred_format"] = "bullet points",
        },
        ["user_002"] = new()
        {
            ["name"]             = "Bob",
            ["language"]         = "English",
            ["expertise"]        = "advanced",
            ["preferred_format"] = "detailed paragraphs",
        },
    };

    private static readonly Dictionary<string, List<string>> _tutorials = new()
    {
        ["python::beginner"] = new()
        {
            "Python Basics: Variables and Types",
            "Your First Python Function",
            "Lists and Loops for Beginners",
        },
        ["python::advanced"] = new()
        {
            "Metaclasses and Descriptors",
            "Async IO Deep Dive",
            "CPython Internals",
        },
    };

    [Tool(Name = "get_user_preferences", Description = "Look up user preferences.")]
    public Dictionary<string, object> GetUserPreferences(string user_id)
    {
        return _users.TryGetValue(user_id, out var v)
            ? v
            : new Dictionary<string, object>
            {
                ["name"] = "Guest", ["expertise"] = "intermediate", ["preferred_format"] = "concise",
            };
    }

    [Tool(Name = "search_tutorials", Description = "Search for tutorials matching a topic and skill level.")]
    public Dictionary<string, object> SearchTutorials(string topic, string level)
    {
        var lvl = string.IsNullOrEmpty(level) ? "intermediate" : level.ToLowerInvariant();
        var key = $"{topic.ToLowerInvariant()}::{lvl}";
        var results = _tutorials.TryGetValue(key, out var r)
            ? r
            : new List<string> { $"General {topic} tutorial" };
        return new Dictionary<string, object>
        {
            ["topic"]     = topic,
            ["level"]     = lvl,
            ["tutorials"] = results,
        };
    }
}
