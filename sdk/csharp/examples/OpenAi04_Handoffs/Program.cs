// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi04 — Handoffs.
//
// An OpenAI Agents SDK triage agent that hands off control to one of
// three specialist sub-agents (order / refund / sales). The OpenAIAgent
// bridge maps .Handoffs(...) into the server's handoff strategy.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var orderAgent = OpenAIAgent.Builder()
    .Name("order_specialist")
    .Instructions(
        "You handle order-related inquiries. Use the check_order_status tool " +
        "to look up orders. Be professional and concise.")
    .Model(Settings.LlmModel)
    .Tools(new OrderTools())
    .Build();

var refundAgent = OpenAIAgent.Builder()
    .Name("refund_specialist")
    .Instructions(
        "You handle refund requests. Use the process_refund tool to initiate " +
        "refunds. Always confirm the order ID and reason before processing.")
    .Model(Settings.LlmModel)
    .Tools(new RefundTools())
    .Build();

var salesAgent = OpenAIAgent.Builder()
    .Name("sales_specialist")
    .Instructions(
        "You handle product inquiries and sales. Use the get_product_info tool " +
        "to look up products. Be enthusiastic but not pushy.")
    .Model(Settings.LlmModel)
    .Tools(new SalesTools())
    .Build();

var triage = OpenAIAgent.Builder()
    .Name("customer_service_triage")
    .Instructions(
        "You are a customer service triage agent. Determine the customer's need " +
        "and hand off to the appropriate specialist:\n" +
        "- Order status inquiries -> order_specialist\n" +
        "- Refund requests -> refund_specialist\n" +
        "- Product questions or purchases -> sales_specialist\n" +
        "Be brief in your initial response before handing off.")
    .Model(Settings.LlmModel)
    .Handoffs(orderAgent, refundAgent, salesAgent)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(
    triage,
    "I'd like a refund for order ORD-002, the product arrived damaged.");
result.PrintResult();

internal sealed class OrderTools
{
    private static readonly Dictionary<string, string> _orders = new()
    {
        ["ORD-001"] = "Shipped - arriving tomorrow",
        ["ORD-002"] = "Processing - estimated ship date: Friday",
        ["ORD-003"] = "Delivered on Monday",
    };

    [Tool(Name = "check_order_status", Description = "Check the status of a customer order.")]
    public string CheckOrderStatus(string order_id)
        => _orders.TryGetValue(order_id, out var v) ? v : $"Order {order_id} not found";
}

internal sealed class RefundTools
{
    [Tool(Name = "process_refund", Description = "Process a refund for an order.")]
    public string ProcessRefund(string order_id, string reason)
        => $"Refund initiated for {order_id}. Reason: {reason}. Expect 3-5 business days.";
}

internal sealed class SalesTools
{
    private static readonly Dictionary<string, string> _products = new(StringComparer.OrdinalIgnoreCase)
    {
        ["laptop pro"]       = "Laptop Pro X1 - $1,299 - 16GB RAM, 512GB SSD, 14\" display",
        ["wireless earbuds"] = "SoundMax Earbuds - $79 - ANC, 24hr battery, Bluetooth 5.3",
        ["smart watch"]      = "TimeSync Watch - $249 - GPS, health tracking, 5-day battery",
    };

    [Tool(Name = "get_product_info", Description = "Get product information and pricing.")]
    public string GetProductInfo(string product_name)
        => _products.TryGetValue(product_name, out var v) ? v : $"Product '{product_name}' not found";
}
