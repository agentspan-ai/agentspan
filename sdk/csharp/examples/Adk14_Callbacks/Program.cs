// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk14 — Callbacks (customer service).
//
// A customer service agent with multiple tools. Note: ADK callbacks
// (before/after_tool_callback, before/after_model_callback) are
// framework-side hooks that may not execute server-side when compiled
// to Conductor workflows; we preserve the tool shapes and example flow.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("customer_service_agent")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a helpful customer service agent. " +
        "Use the available tools to look up customer information, " +
        "check order status, and apply discounts when requested. " +
        "Always verify the customer exists before applying discounts.")
    .Tools(new CustomerTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "Look up customer C001 and check if order ORD-1001 has shipped. " +
    "If the customer is gold tier, apply a 10% discount.");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class CustomerTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _customers = new(StringComparer.OrdinalIgnoreCase)
    {
        ["C001"] = new() { ["name"] = "Alice Smith", ["tier"] = "gold",   ["balance"] = 1500.00 },
        ["C002"] = new() { ["name"] = "Bob Jones",   ["tier"] = "silver", ["balance"] = 320.50  },
        ["C003"] = new() { ["name"] = "Carol White", ["tier"] = "bronze", ["balance"] = 50.00   },
    };
    private static readonly Dictionary<string, Dictionary<string, object?>> _orders = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ORD-1001"] = new() { ["status"] = "shipped",    ["tracking"] = "TRK-98765", ["eta"] = "2025-04-20" },
        ["ORD-1002"] = new() { ["status"] = "processing", ["tracking"] = null,        ["eta"] = "2025-04-25" },
    };

    [Tool(Name = "lookup_customer", Description = "Look up customer information by ID.")]
    public Dictionary<string, object> LookupCustomer(string customer_id)
    {
        if (!_customers.TryGetValue(customer_id, out var customer))
            return new Dictionary<string, object> { ["found"] = false, ["error"] = $"Customer {customer_id} not found" };
        var result = new Dictionary<string, object> { ["found"] = true, ["customer_id"] = customer_id };
        foreach (var (k, v) in customer) result[k] = v;
        return result;
    }

    [Tool(Name = "apply_discount", Description = "Apply a discount to a customer's account.")]
    public Dictionary<string, object> ApplyDiscount(string customer_id, double discount_percent)
    {
        if (discount_percent > 50)
            return new Dictionary<string, object> { ["error"] = "Discount cannot exceed 50%" };
        return new Dictionary<string, object>
        {
            ["status"]           = "success",
            ["customer_id"]      = customer_id,
            ["discount_applied"] = $"{discount_percent}%",
            ["message"]          = $"Applied {discount_percent}% discount to {customer_id}",
        };
    }

    [Tool(Name = "check_order_status", Description = "Check the status of an order.")]
    public Dictionary<string, object?> CheckOrderStatus(string order_id)
    {
        return _orders.TryGetValue(order_id, out var v)
            ? v
            : new Dictionary<string, object?> { ["error"] = $"Order {order_id} not found" };
    }
}
