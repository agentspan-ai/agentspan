// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk16 — Customer Service.
//
// A single agent with multiple domain-specific tools that handles
// customer inquiries end-to-end (account, billing, ticket, plan).
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("customer_service_rep")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a customer service representative for CloudServe Inc. " +
        "Help customers with account inquiries, billing questions, plan changes, " +
        "and support tickets. Always verify the account exists before making changes. " +
        "Be professional and empathetic.")
    .Tools(new CsTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "I'm customer ACC-001. Can you check my billing history and tell me my current plan? " +
    "I'm thinking about downgrading to the basic plan.");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class CsTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _accounts = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ACC-001"] = new()
        {
            ["name"]    = "Alice Johnson",
            ["email"]   = "alice@example.com",
            ["plan"]    = "Premium",
            ["balance"] = 142.50,
            ["status"]  = "active",
        },
        ["ACC-002"] = new()
        {
            ["name"]    = "Bob Martinez",
            ["email"]   = "bob@example.com",
            ["plan"]    = "Basic",
            ["balance"] = 0.00,
            ["status"]  = "active",
        },
    };
    private static readonly Dictionary<string, List<Dictionary<string, object>>> _history = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ACC-001"] = new()
        {
            new() { ["month"] = "March 2025",    ["amount"] = 49.99, ["status"] = "paid" },
            new() { ["month"] = "February 2025", ["amount"] = 49.99, ["status"] = "paid" },
            new() { ["month"] = "January 2025",  ["amount"] = 42.50, ["status"] = "paid" },
        },
    };

    [Tool(Name = "get_account_details", Description = "Retrieve account details for a customer.")]
    public Dictionary<string, object> GetAccountDetails(string account_id)
        => _accounts.TryGetValue(account_id, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Account {account_id} not found" };

    [Tool(Name = "get_billing_history", Description = "Get billing history for an account.")]
    public Dictionary<string, object> GetBillingHistory(string account_id, int num_months)
    {
        var records = _history.TryGetValue(account_id, out var v) ? v : new List<Dictionary<string, object>>();
        var n = num_months <= 0 ? 3 : num_months;
        return new Dictionary<string, object>
        {
            ["account_id"]      = account_id,
            ["billing_history"] = records.Take(n).ToList(),
        };
    }

    [Tool(Name = "submit_support_ticket", Description = "Submit a support ticket for a customer issue.")]
    public Dictionary<string, object> SubmitSupportTicket(string account_id, string category, string description)
    {
        var valid = new[] { "billing", "technical", "account", "general" };
        if (!valid.Contains(category.ToLowerInvariant()))
            return new Dictionary<string, object> { ["error"] = $"Invalid category. Must be one of: {string.Join(", ", valid)}" };
        return new Dictionary<string, object>
        {
            ["ticket_id"]  = "TKT-2025-0042",
            ["account_id"] = account_id,
            ["category"]   = category,
            ["status"]     = "open",
            ["message"]    = $"Ticket created for {category} issue",
        };
    }

    [Tool(Name = "update_account_plan", Description = "Update the subscription plan for an account.")]
    public Dictionary<string, object> UpdateAccountPlan(string account_id, string new_plan)
    {
        var plans = new Dictionary<string, double>
        {
            ["basic"] = 19.99, ["premium"] = 49.99, ["enterprise"] = 99.99,
        };
        if (!plans.TryGetValue(new_plan.ToLowerInvariant(), out var price))
            return new Dictionary<string, object> { ["error"] = $"Invalid plan. Available: {string.Join(", ", plans.Keys)}" };
        return new Dictionary<string, object>
        {
            ["status"]         = "success",
            ["account_id"]     = account_id,
            ["new_plan"]       = new_plan,
            ["new_price"]      = $"${price}/month",
            ["effective_date"] = "Next billing cycle",
        };
    }
}
