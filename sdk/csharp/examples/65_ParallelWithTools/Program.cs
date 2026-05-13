// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Parallel Agents with Tools — each branch has its own domain tools.
//
// Extends the basic parallel pattern by giving each parallel branch its own
// tools. All branches run concurrently and each independently calls its tools.
//
// Architecture:
//   parallel_analysis
//   ├── financial_analyst  (tools: [check_balance])
//   └── order_analyst      (tools: [lookup_order])
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Parallel branches with domain tools ───────────────────────

var financialAnalyst = new Agent("financial_analyst_65")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a financial analyst. Use check_balance to look up account " +
        "balances and provide a financial summary.",
    Tools = ToolRegistry.FromInstance(new FinancialTools65()),
};

var orderAnalyst = new Agent("order_analyst_65")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are an order analyst. Use lookup_order to check order status " +
        "and provide an order summary.",
    Tools = ToolRegistry.FromInstance(new OrderTools65()),
};

// ── Parallel orchestrator ──────────────────────────────────────

var parallelAnalysis = new Agent("parallel_analysis_65")
{
    Agents   = [financialAnalyst, orderAnalyst],
    Strategy = Strategy.Parallel,
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    parallelAnalysis,
    "Customer ID: CUST-789. Check both their balance (account ACC-789) " +
    "and their most recent order (ORD-789).");

result.PrintResult();

// ── Tool classes ──────────────────────────────────────────────

internal sealed class FinancialTools65
{
    [Tool("Check the balance of a bank account.")]
    public Dictionary<string, object> CheckBalance(string accountId)
        => new() { ["account_id"] = accountId, ["balance"] = 5432.10, ["currency"] = "USD" };
}

internal sealed class OrderTools65
{
    [Tool("Look up the status of an order.")]
    public Dictionary<string, object> LookupOrder(string orderId)
        => new() { ["order_id"] = orderId, ["status"] = "shipped", ["eta"] = "2 days" };
}
