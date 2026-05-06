// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// External Worker Tools — reference workers running in other services.
//
// [Tool(External = true)] on a no-op method gives the agent a tool stub
// with schema and description but starts NO local worker. Conductor
// dispatches the task to whatever process is already polling for it —
// a Java service, a Go worker, another team's microservice, etc.
//
// This is useful when:
//   - Workers are written in another language
//   - Workers run in a separate microservice
//   - You want to reuse existing Conductor task definitions
//
// Requirements:
//   - Agentspan server with LLM support
//   - External workers for process_order, delete_account, get_customer,
//     and check_inventory must be running elsewhere
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Agent: local + external tools ────────────────────────────────────

var supportAgent = new Agent("support_agent")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new SupportTools()),
    Instructions =
        "You are a customer support agent. Use the available tools to " +
        "look up customers, check inventory, process orders, and format " +
        "responses for the customer.",
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("=== External Worker Tools ===");
Console.WriteLine("Agent has 1 local tool + 3 external worker references.\n");

var result = await runtime.RunAsync(
    supportAgent,
    "Customer C-1234 wants to cancel order ORD-5678. " +
    "Look up the customer, check if we have the product in stock, " +
    "and process the cancellation.");

result.PrintResult();

// ── Tool class ────────────────────────────────────────────────────────

internal sealed class SupportTools
{
    // Local tool — runs in this process
    [Tool("Format a data dictionary into a human-readable string.")]
    public string FormatResponse(string data) =>
        $"Formatted: {data}";

    // External tools — stubs only; workers run elsewhere
    // The method body is never called; the schema comes from the parameters.

    [Tool("Look up customer details from the CRM system.", External = true)]
    public Dictionary<string, object> GetCustomer(string customerId) => default!;

    [Tool("Check product availability in a warehouse.", External = true)]
    public Dictionary<string, object> CheckInventory(string productId, string warehouse = "default") => default!;

    [Tool("Process a customer order. Actions: refund, cancel, update.", External = true)]
    public Dictionary<string, object> ProcessOrder(string orderId, string action) => default!;

    [Tool("Permanently delete a user account. Requires manager approval.",
          External = true, ApprovalRequired = true)]
    public Dictionary<string, object> DeleteAccount(string userId, string reason) => default!;
}
