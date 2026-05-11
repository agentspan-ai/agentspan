// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Prompt Templates — use server-side templates for agent instructions.
//
// Instead of embedding instructions inline, agents can reference a
// named template stored on the Conductor server. Variables substitute
// ${var} placeholders at execution time, letting you update wording
// centrally without redeploying code.
//
// Requires a template named "order-support" on the server.
// Create it in the Conductor UI (Definitions → Prompt Templates) with body:
//
//   You are an order support specialist.
//   Maximum refund authority: ${max_refund}.
//   For escalations, contact: ${escalation_email}.
//
// If the template is absent the agent still runs with server defaults.
//
// Requirements:
//   - Agentspan server with the "order-support" prompt template defined
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Agent with prompt template ────────────────────────────────

var tools = ToolRegistry.FromInstance(new OrderTools());

var orderAgent = new Agent("order_assistant_34")
{
    Model = Settings.LlmModel,
    PromptTemplateInstructions = new PromptTemplate(
        Name:      "order-support",
        Variables: new() {
            ["max_refund"]        = "$500",
            ["escalation_email"]  = "help@acme.com",
        }
    ),
    Tools = [.. tools],
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

var result = await runtime.RunAsync(orderAgent, "Can you check order #12345?");
result.PrintResult();

// ── Tool class ────────────────────────────────────────────────

internal sealed class OrderTools
{
    [Tool("Look up an order by ID.")]
    public object LookupOrder(string orderId) =>
        new { order_id = orderId, status = "shipped", eta = "2 days" };

    [Tool("Look up customer details by email.")]
    public object LookupCustomer(string email) =>
        new { email, name = "Jane Doe", tier = "premium" };
}
