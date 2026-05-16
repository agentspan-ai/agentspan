// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Multi-Step Tool Calling — chained lookups and calculations.
//
// The agent has four tools. The prompt requires it to:
// 1. Look up a customer's account
// 2. Fetch their recent transactions
// 3. Calculate the total spend
// 4. Formulate a final answer using all the data
//
// This shows the agent loop in action: the LLM calls tools one at a
// time, feeds each result into the next decision, and stops when it has
// enough information to answer.
//
// In the Conductor UI you'll see each tool call as a separate DynamicTask
// with clear inputs/outputs, making it easy to trace the reasoning chain.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("account_analyst_02b")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new AccountTools()),
    Instructions =
        "You are an account analyst. When asked about a customer, look them up, " +
        "fetch their transactions, calculate the total, and provide a summary. " +
        "Use the tools step by step.",
};

await using var runtime = new AgentRuntime();

var result = await runtime.RunAsync(
    agent,
    "How much has alice@example.com spent recently? " +
    "Get her last 3 transactions and give me the total.");
result.PrintResult();

// ── Tool class ─────────────────────────────────────────────────

internal sealed class AccountTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> Customers = new()
    {
        ["alice@example.com"] = new() { ["id"] = "CUST-001", ["name"] = "Alice Johnson", ["tier"] = "gold" },
        ["bob@example.com"]   = new() { ["id"] = "CUST-002", ["name"] = "Bob Smith",    ["tier"] = "silver" },
    };

    private static readonly Dictionary<string, List<Dictionary<string, object>>> Transactions = new()
    {
        ["CUST-001"] =
        [
            new() { ["date"] = "2026-02-15", ["amount"] = 120.00, ["merchant"] = "Cloud Services Inc" },
            new() { ["date"] = "2026-02-12", ["amount"] = 45.50,  ["merchant"] = "Office Supplies Co" },
            new() { ["date"] = "2026-02-10", ["amount"] = 230.00, ["merchant"] = "Dev Tools Ltd" },
        ],
    };

    [Tool("Look up a customer by email address.")]
    public Dictionary<string, object> LookupCustomer(string email)
        => Customers.TryGetValue(email, out var c) ? c
           : new() { ["error"] = $"No customer found for {email}" };

    [Tool("Get recent transactions for a customer.")]
    public Dictionary<string, object> GetTransactions(string customerId, int limit)
    {
        var txns = Transactions.TryGetValue(customerId, out var t) ? t : [];
        return new() { ["customer_id"] = customerId, ["transactions"] = txns.Take(limit).ToList() };
    }

    [Tool("Calculate the sum of a list of amounts.")]
    public Dictionary<string, object> CalculateTotal(List<double> amounts)
        => new() { ["total"] = Math.Round(amounts.Sum(), 2), ["count"] = amounts.Count };

    [Tool("Send a summary email to a customer.")]
    public Dictionary<string, object> SendSummaryEmail(string to, string subject, string body)
        => new() { ["status"] = "sent", ["to"] = to, ["subject"] = subject };
}
