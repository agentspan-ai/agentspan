// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk15 — Global Instruction.
//
// ADK's global_instruction for system-wide context. The GoogleADKAgent
// builder exposes a single Instruction; we concatenate the global +
// per-agent instruction to preserve the intent.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

const string globalInstruction =
    "You work for TechStore, a premium electronics retailer. " +
    "Always be professional and mention our satisfaction guarantee. " +
    "Current promotion: 15% off all electronics this week.";

const string perAgentInstruction =
    "You are a store assistant. Help customers find products, " +
    "check availability, and provide store hours. " +
    "Always mention the current promotion when discussing electronics.";

var agent = GoogleADKAgent.Builder()
    .Name("store_assistant")
    .Model(Settings.LlmModel)
    .Instruction($"{globalInstruction}\n\n{perAgentInstruction}")
    .Tools(new StoreTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "I'm looking for the Widget Pro. Is it in stock? Also, what are the downtown store hours?");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class StoreTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _products = new(StringComparer.OrdinalIgnoreCase)
    {
        ["widget pro"] = new()
        {
            ["name"] = "Widget Pro", ["price"] = 49.99, ["category"] = "electronics",
            ["in_stock"] = true, ["rating"] = 4.7,
        },
        ["gadget max"] = new()
        {
            ["name"] = "Gadget Max", ["price"] = 89.99, ["category"] = "electronics",
            ["in_stock"] = false, ["rating"] = 4.2,
        },
        ["smart lamp"] = new()
        {
            ["name"] = "Smart Lamp", ["price"] = 34.99, ["category"] = "home",
            ["in_stock"] = true, ["rating"] = 4.5,
        },
    };
    private static readonly Dictionary<string, Dictionary<string, object>> _stores = new(StringComparer.OrdinalIgnoreCase)
    {
        ["downtown"] = new() { ["hours"] = "9 AM - 9 PM",  ["open_today"] = true },
        ["mall"]     = new() { ["hours"] = "10 AM - 8 PM", ["open_today"] = true },
    };

    [Tool(Name = "get_product_info", Description = "Look up product information.")]
    public Dictionary<string, object> GetProductInfo(string product_name)
        => _products.TryGetValue(product_name, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Product '{product_name}' not found" };

    [Tool(Name = "get_store_hours", Description = "Get store hours for a location.")]
    public Dictionary<string, object> GetStoreHours(string location)
        => _stores.TryGetValue(location, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Location '{location}' not found" };
}
