// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Agent Lifecycle Callbacks — before/after model hooks with timing and logging.
//
// Demonstrates using BeforeModelCallback and AfterModelCallback as
// composable lifecycle hooks. Multiple concerns (timing, logging) are
// handled independently in a chainable pattern.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using Agentspan;
using Agentspan.Examples;

// ── Shared timing state ───────────────────────────────────────
var t0 = DateTime.UtcNow;

// ── Agent with chained lifecycle callbacks ────────────────────

var agent = new Agent("lifecycle_agent_53")
{
    Model        = Settings.LlmModel,
    Instructions = "You are a helpful assistant. Use lookup_weather for weather queries.",
    Tools        = ToolRegistry.FromInstance(new WeatherTools()),

    // Timing + logging before each LLM call
    BeforeModelCallback = messages =>
    {
        t0 = DateTime.UtcNow;
        int count = messages?.Count ?? 0;
        Console.WriteLine($"  [timing] Agent started");
        Console.WriteLine($"  [log] Sending {count} messages to LLM");
        return [];  // continue normally
    },

    // Timing + logging after each LLM call
    AfterModelCallback = llmResult =>
    {
        var elapsed = (DateTime.UtcNow - t0).TotalSeconds;
        var snippet = llmResult is not null && llmResult.Length > 80
            ? llmResult[..80]
            : llmResult ?? "";
        Console.WriteLine($"  [timing] Agent finished — {elapsed:F2}s");
        Console.WriteLine($"  [log] LLM responded: \"{snippet}\"");
        return [];  // keep original response
    },
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What's the weather like in Tokyo?");
result.PrintResult();

// ── Tool class ────────────────────────────────────────────────

internal sealed class WeatherTools
{
    [Tool("Get the current weather for a city.")]
    public Dictionary<string, object> LookupWeather(string city)
        => new() { ["city"] = city, ["temperature"] = "22C", ["condition"] = "sunny" };
}
