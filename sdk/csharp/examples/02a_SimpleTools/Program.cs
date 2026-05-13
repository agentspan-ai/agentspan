// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Simple Tool Calling — two tools, the LLM picks the right one.
//
// The agent has two tools: one for weather, one for stock prices.
// Based on the user's question, the LLM decides which tool to call.
//
// In the Conductor UI you'll see each tool call as a separate task
// (DynamicTask) with its inputs and outputs clearly visible.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional)

using Agentspan;
using Agentspan.Examples;

// ── Tool definitions on a simple class ─────────────────────────────

var tools = ToolRegistry.FromInstance(new SimpleToolHost());

// ── Agent ───────────────────────────────────────────────────────────

var agent = new Agent("weather_stock_agent")
{
    Model = Settings.LlmModel,
    Instructions = "You are a helpful assistant. Use tools to answer questions.",
    Tools = tools,
};

// ── Run — the LLM will call GetWeather (not GetStockPrice) ─────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What's the weather like in San Francisco?");
result.PrintResult();

// ── Tool host ───────────────────────────────────────────────────────

internal sealed class SimpleToolHost
{
    [Tool("Get the current weather for a city.")]
    public Dictionary<string, object> GetWeather(string city)
        => new() { ["city"] = city, ["temp_f"] = 72, ["condition"] = "Sunny" };

    [Tool("Get the current stock price for a ticker symbol.")]
    public Dictionary<string, object> GetStockPrice(string symbol)
        => new() { ["symbol"] = symbol, ["price"] = 182.50, ["change"] = "+1.2%" };
}
