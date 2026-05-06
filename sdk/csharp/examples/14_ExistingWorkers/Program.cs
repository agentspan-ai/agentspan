// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Existing Workers — mix tools from separate worker modules.
//
// In production each tool class might live in its own service/deployment.
// This example shows how to combine tools from multiple tool hosts and
// pass them to a single agent — no re-wrapping needed.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Tool hosts (could each be in their own service) ───────────────────

var crmTools     = ToolRegistry.FromInstance(new CrmWorker());
var orderTools   = ToolRegistry.FromInstance(new OrderWorker());
var supportTools = ToolRegistry.FromInstance(new SupportWorker());

// Combine tools from all three workers into one agent
var allTools = new List<ToolDef>();
allTools.AddRange(crmTools);
allTools.AddRange(orderTools);
allTools.AddRange(supportTools);

// ── Agent ─────────────────────────────────────────────────────────────

var agent = new Agent("customer_support")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a customer support agent. Use the available tools to look up " +
        "customer information, check order history, and create support tickets.",
    Tools = allTools,
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    agent,
    "Customer C001 is asking about their recent orders. Look them up and summarize.");

result.PrintResult();

// ── Worker tool classes ───────────────────────────────────────────────

/// <summary>CRM service — customer data lookup.</summary>
internal sealed class CrmWorker
{
    private static readonly Dictionary<string, Dictionary<string, object>> _customers = new()
    {
        ["C001"] = new() { ["name"] = "Alice", ["plan"] = "Enterprise", ["since"] = "2021-03" },
        ["C002"] = new() { ["name"] = "Bob",   ["plan"] = "Starter",    ["since"] = "2023-11" },
    };

    [Tool("Fetch customer profile from the CRM database.")]
    public Dictionary<string, object> GetCustomerData(string customerId) =>
        _customers.TryGetValue(customerId, out var c) ? c : new() { ["error"] = "Customer not found" };
}

/// <summary>Order service — order history lookup.</summary>
internal sealed class OrderWorker
{
    private static readonly Dictionary<string, List<Dictionary<string, object>>> _orders = new()
    {
        ["C001"] =
        [
            new() { ["id"] = "ORD-101", ["amount"] = 250.00, ["status"] = "delivered" },
            new() { ["id"] = "ORD-098", ["amount"] = 89.99,  ["status"] = "delivered" },
        ],
        ["C002"] =
        [
            new() { ["id"] = "ORD-110", ["amount"] = 45.00, ["status"] = "shipped" },
        ],
    };

    [Tool("Retrieve recent order history for a customer.")]
    public Dictionary<string, object> GetOrderHistory(string customerId, int limit = 5)
    {
        var orders = _orders.TryGetValue(customerId, out var o) ? o.Take(limit).ToList() : [];
        return new() { ["customer_id"] = customerId, ["orders"] = orders };
    }
}

/// <summary>Support service — ticket creation.</summary>
internal sealed class SupportWorker
{
    [Tool("Create a support ticket for a customer issue.")]
    public Dictionary<string, object> CreateSupportTicket(
        string customerId, string issue, string priority = "medium") =>
        new()
        {
            ["ticket_id"]   = "TKT-999",
            ["customer_id"] = customerId,
            ["issue"]       = issue,
            ["priority"]    = priority,
        };
}
