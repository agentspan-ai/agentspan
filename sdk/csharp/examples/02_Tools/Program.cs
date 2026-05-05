// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Tools — multiple tools, LLM picks which to call.
//
// Demonstrates:
//   - Multiple [Tool] methods on a class
//   - Approval-required tools (human-in-the-loop)
//   - Streaming events to observe the agent's reasoning
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional)

using Agentspan;
using Agentspan.Examples;

// ── Tool definitions ────────────────────────────────────────────────

var toolHost = new ToolHost();
var tools = ToolRegistry.FromInstance(toolHost);

// ── Agent ───────────────────────────────────────────────────────────

var agent = new Agent("tool_demo_agent")
{
    Model = Settings.LlmModel,
    Instructions = "You are a helpful assistant with access to weather, calculator, and email tools.",
    Tools = tools,
};

// ── Run with streaming ──────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var handle = await runtime.StartAsync(agent, "What's the weather in New York, and what's sqrt(144)?");

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
        case EventType.Done:
            Console.WriteLine($"\nDone: {ev.Content ?? ev.Output?.ToString()}");
            break;
    }
}

// ── Tool host class ─────────────────────────────────────────────────

internal sealed class ToolHost
{
    private static readonly Dictionary<string, (int temp, string condition)> _weather = new(StringComparer.OrdinalIgnoreCase)
    {
        ["new york"]     = (72, "Partly Cloudy"),
        ["san francisco"] = (58, "Foggy"),
        ["miami"]        = (85, "Sunny"),
    };

    [Tool("Get current weather for a city.")]
    public Dictionary<string, object> GetWeather(string city)
    {
        if (!_weather.TryGetValue(city, out var data))
            data = (70, "Clear");
        return new Dictionary<string, object>
        {
            ["city"] = city,
            ["temperature_f"] = data.temp,
            ["condition"] = data.condition,
        };
    }

    [Tool("Evaluate a safe math expression.")]
    public Dictionary<string, object> Calculate(string expression)
    {
        // Minimal safe evaluator for demonstration
        try
        {
            // Only handle sqrt(N) for this demo
            if (expression.StartsWith("sqrt(") && expression.EndsWith(")"))
            {
                var inner = double.Parse(expression[5..^1]);
                return new Dictionary<string, object> { ["expression"] = expression, ["result"] = Math.Sqrt(inner) };
            }
            return new Dictionary<string, object> { ["expression"] = expression, ["error"] = "Unsupported expression" };
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object> { ["expression"] = expression, ["error"] = ex.Message };
        }
    }

    [Tool("Send an email to the specified address.", ApprovalRequired = true, TimeoutSeconds = 60)]
    public Dictionary<string, object> SendEmail(string to, string subject, string body)
    {
        // In production, this would actually send an email
        Console.WriteLine($"  [email] Sending to {to}: {subject}");
        return new Dictionary<string, object> { ["status"] = "sent", ["to"] = to, ["subject"] = subject };
    }
}
