// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Swarm with Tools — sub-agents have their own domain tools.
//
// Extends the basic swarm pattern by giving each specialist its own tools.
// The swarm transfer mechanism works alongside the tools: the LLM can
// call domain tools AND transfer tools in the same turn.
//
// Flow:
//   1. Front-line support triages the request
//   2. Calls transfer_to_billing_specialist or transfer_to_order_specialist
//   3. Specialist uses its domain tool (check_balance / lookup_order)
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Specialist agents with domain tools ───────────────────────

var billingSpecialist = new Agent("billing_specialist_64")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a billing specialist. Use check_balance to look up account " +
        "balances and help customers with financial inquiries.",
    Tools = ToolRegistry.FromInstance(new BillingTools()),
};

var orderSpecialist = new Agent("order_specialist_64")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are an order specialist. Use lookup_order to check order status " +
        "and help customers with order-related inquiries.",
    Tools = ToolRegistry.FromInstance(new OrderTools()),
};

// ── Front-line support (swarm coordinator) ────────────────────

var frontLine = new Agent("front_line_64")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are the front-line customer support agent. Triage requests. " +
        "For billing questions, transfer to billing_specialist_64. " +
        "For order questions, transfer to order_specialist_64.",
    Agents   = [billingSpecialist, orderSpecialist],
    Strategy = Strategy.Swarm,
    MaxTurns = 5,
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Billing Query ---");
var result1 = await runtime.RunAsync(
    frontLine,
    "What's the balance on account ACC-123?");
result1.PrintResult();

Console.WriteLine("\n--- Order Query ---");
var result2 = await runtime.RunAsync(
    frontLine,
    "What's the status of order ORD-456?");
result2.PrintResult();

// ── Tool classes ──────────────────────────────────────────────

internal sealed class BillingTools
{
    [Tool("Check the balance of a bank account.")]
    public Dictionary<string, object> CheckBalance(string accountId)
        => new() { ["account_id"] = accountId, ["balance"] = 5432.10, ["currency"] = "USD" };
}

internal sealed class OrderTools
{
    [Tool("Look up the status of an order.")]
    public Dictionary<string, object> LookupOrder(string orderId)
        => new() { ["order_id"] = orderId, ["status"] = "shipped", ["eta"] = "2 days" };
}
