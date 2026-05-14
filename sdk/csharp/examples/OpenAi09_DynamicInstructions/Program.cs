// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi09 — Dynamic Instructions.
//
// Instructions computed at build time from the current time-of-day so
// the agent adopts a cheerful morning / focused afternoon / calm
// evening persona. A pair of todo-list tools is also wired up.
//
// Note: simplified from Java original — Python's per-turn dynamic
// callable for instructions has no direct OpenAIAgent equivalent; we
// resolve the dynamic prompt once at startup (semantically equivalent
// for a single-shot run).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var agent = OpenAIAgent.Builder()
    .Name("personal_assistant")
    .Instructions(GetDynamicInstructions())
    .Model(Settings.LlmModel)
    .Tools(new TodoTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(
    agent,
    "Show me my todo list and add 'Prepare demo for Friday' as high priority.");
result.PrintResult();

static string GetDynamicInstructions()
{
    var now = DateTime.Now;
    var hour = now.Hour;
    string greetingStyle;
    string tone;
    if (hour < 12)
    {
        greetingStyle = "cheerful morning";
        tone = "energetic and upbeat";
    }
    else if (hour < 17)
    {
        greetingStyle = "professional afternoon";
        tone = "focused and efficient";
    }
    else
    {
        greetingStyle = "relaxed evening";
        tone = "calm and conversational";
    }
    var timeStr = now.ToString("hh:mm tt");
    return $"You are a personal assistant with a {greetingStyle} style. " +
           $"Respond in a {tone} tone. " +
           $"Current time: {timeStr}. " +
           "Always be helpful and use available tools when appropriate.";
}

internal sealed class TodoTools
{
    [Tool(Name = "get_todo_list", Description = "Get the user's current todo list.")]
    public string GetTodoList()
    {
        var todos = new[]
        {
            "Review PR #42 - high priority",
            "Write unit tests for auth module",
            "Team standup at 2pm",
            "Deploy v2.1 to staging",
        };
        return string.Join("\n", todos.Select(t => $"- {t}"));
    }

    [Tool(Name = "add_todo", Description = "Add a new item to the todo list.")]
    public string AddTodo(string task, string priority)
    {
        var p = string.IsNullOrEmpty(priority) ? "medium" : priority;
        return $"Added to todo list: '{task}' (priority: {p})";
    }
}
