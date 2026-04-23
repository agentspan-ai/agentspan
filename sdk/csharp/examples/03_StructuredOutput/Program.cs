// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Structured Output — typed JSON response from the agent.
//
// Demonstrates how to ask the agent to return a structured JSON object
// (C# record) instead of free-form text. The server enforces the schema.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using System.Text.Json.Serialization;
using Agentspan;
using Agentspan.Examples;

// ── Tool ─────────────────────────────────────────────────────────────

var tools = ToolRegistry.FromInstance(new WeatherTools());

// ── Agent with output_type ───────────────────────────────────────────

var agent = new Agent("weather_reporter")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a weather reporter. Get the weather and provide a brief recommendation.",
    Tools        = tools,
    OutputType   = typeof(WeatherReport),
};

// ── Run ──────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What's the weather in NYC?");

Console.WriteLine($"Status: {result.Status}");

// The structured output lands in result.Output["result"] as a JSON string
if (result.Output?.TryGetValue("result", out var raw) == true)
{
    var report = JsonSerializer.Deserialize<WeatherReport>(raw?.ToString() ?? "{}", AgentspanJson.Options);
    if (report is not null)
    {
        Console.WriteLine($"City:           {report.City}");
        Console.WriteLine($"Temperature:    {report.Temperature}°F");
        Console.WriteLine($"Condition:      {report.Condition}");
        Console.WriteLine($"Recommendation: {report.Recommendation}");
        return;
    }
}

result.PrintResult();

// ── Types and classes ────────────────────────────────────────────────

internal record WeatherReport(
    [property: JsonPropertyName("city")]           string City,
    [property: JsonPropertyName("temperature")]    double Temperature,
    [property: JsonPropertyName("condition")]      string Condition,
    [property: JsonPropertyName("recommendation")] string Recommendation
);

internal sealed class WeatherTools
{
    [Tool("Get current weather data for a city.")]
    public Dictionary<string, object> GetWeather(string city) =>
        new()
        {
            ["city"]      = city,
            ["temp_f"]    = 72,
            ["condition"] = "Sunny",
            ["humidity"]  = 45,
        };
}
