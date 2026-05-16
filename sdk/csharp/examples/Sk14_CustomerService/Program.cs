// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk14 — Customer service agent over a mock backend.
//
// Plugin functions look up orders, issue refunds, and escalate tickets.
// The agent decides the right sequence of calls for a customer message.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk14;

public sealed class SupportPlugin
{
    private static readonly Dictionary<string, (string status, decimal total)> Orders = new()
    {
        ["A-1001"] = ("delivered", 89.99m),
        ["A-1002"] = ("shipped",   42.00m),
        ["A-1003"] = ("cancelled", 15.50m),
    };

    [KernelFunction, Description("Look up an order by id. Returns 'NOT_FOUND' if unknown.")]
    public string LookupOrder([Description("order id e.g. A-1001")] string orderId)
    {
        if (!Orders.TryGetValue(orderId, out var row)) return "NOT_FOUND";
        return $"order={orderId} status={row.status} total={row.total:0.00}";
    }

    [KernelFunction, Description("Issue a refund. Returns confirmation id.")]
    public string IssueRefund(
        [Description("order id")] string orderId,
        [Description("refund amount")] decimal amount)
        => $"REFUND-{orderId}-{amount:0.00}-OK";

    [KernelFunction, Description("Escalate a ticket to a human agent.")]
    public string Escalate(
        [Description("ticket subject")] string subject,
        [Description("priority: low|normal|high")] string priority = "normal")
        => $"escalated subject='{subject}' priority={priority} ticket=ESC-{Guid.NewGuid().ToString()[..6]}";
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_support",
            model:        Settings.LlmModel,
            instructions: "Help customers. Use lookup_order to check status; refund if delivered with a complaint; escalate if status is unknown.",
            new SupportPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "My order A-1001 arrived damaged. Can you refund it?");
        result.PrintResult();
    }
}
