// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Handoffs — agent delegating to sub-agents.
//
// Demonstrates the HANDOFF strategy where the parent agent's LLM decides
// which sub-agent to delegate to. Sub-agents appear as callable tools.
//
// Architecture:
//   support (HANDOFF)
//   ├── billing   — balance, payments
//   ├── technical — orders, shipping
//   └── sales     — pricing, promotions
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional)

using Agentspan;
using Agentspan.Examples;

// ── Sub-agent tool hosts ────────────────────────────────────────────

var billingTools    = ToolRegistry.FromInstance(new BillingTools());
var technicalTools  = ToolRegistry.FromInstance(new TechnicalTools());
var salesTools      = ToolRegistry.FromInstance(new SalesTools());

// ── Specialist agents ───────────────────────────────────────────────

var billingAgent = new Agent("billing")
{
    Model = Settings.LlmModel,
    Instructions = "You handle billing questions: balances, payments, invoices.",
    Tools = billingTools,
};

var technicalAgent = new Agent("technical")
{
    Model = Settings.LlmModel,
    Instructions = "You handle technical questions: order status, shipping, returns.",
    Tools = technicalTools,
};

var salesAgent = new Agent("sales")
{
    Model = Settings.LlmModel,
    Instructions = "You handle sales questions: pricing, products, promotions.",
    Tools = salesTools,
};

// ── Orchestrator with handoffs ──────────────────────────────────────

var support = new Agent("support")
{
    Model = Settings.LlmModel,
    Instructions = "Route customer requests to the right specialist: billing, technical, or sales.",
    Agents = [billingAgent, technicalAgent, salesAgent],
    Strategy = Strategy.Handoff,
};

// ── Run ─────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(support, "What's the balance on account ACC-123?");
result.PrintResult();

// ── Tool hosts ──────────────────────────────────────────────────────

internal sealed class BillingTools
{
    [Tool("Check the balance of a bank account.")]
    public Dictionary<string, object> CheckBalance(string accountId)
        => new() { ["account_id"] = accountId, ["balance"] = 5432.10, ["currency"] = "USD" };
}

internal sealed class TechnicalTools
{
    [Tool("Look up the status of an order.")]
    public Dictionary<string, object> LookupOrder(string orderId)
        => new() { ["order_id"] = orderId, ["status"] = "shipped", ["eta"] = "2 days" };
}

internal sealed class SalesTools
{
    [Tool("Get pricing information for a product.")]
    public Dictionary<string, object> GetPricing(string product)
        => new() { ["product"] = product, ["price"] = 99.99, ["discount"] = "10% off" };
}
