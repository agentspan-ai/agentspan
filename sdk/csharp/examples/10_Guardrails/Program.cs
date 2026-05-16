// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Guardrails — output validation with retry.
//
// A PII guardrail checks the agent's final output. If the agent includes
// a raw credit card number, the guardrail fails with OnFail.Retry and the
// agent retries with feedback asking it to redact the PII.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.RegularExpressions;
using Agentspan;
using Agentspan.Examples;

// ── Tools ────────────────────────────────────────────────────────────

var toolHost      = new SupportTools();
var guardrailHost = new PiiGuardrails();

var tools      = ToolRegistry.FromInstance(toolHost);
var guardrails = GuardrailRegistry.FromInstance(guardrailHost);

// ── Agent ─────────────────────────────────────────────────────────────

var agent = new Agent("support_agent")
{
    Model      = Settings.LlmModel,
    Instructions =
        "You are a customer support assistant. Use the available tools to " +
        "answer questions about orders and customers. Always include all " +
        "details from the tool results in your response.",
    Tools      = tools,
    Guardrails = guardrails,
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    agent,
    "I need a full summary: What's the status of order ORD-42, " +
    "and what's the profile for customer CUST-7?");

result.PrintResult();

// Verify the guardrail worked
var output = result.Output?.GetValueOrDefault("result")?.ToString() ?? "";
if (output.Contains("4532-0150-1234-5678"))
    Console.WriteLine("[WARN] PII leaked through the guardrail!");
else
    Console.WriteLine("[OK] PII was redacted from the final output.");

// ── Classes ───────────────────────────────────────────────────────────

internal sealed class SupportTools
{
    [Tool("Look up the current status of an order.")]
    public Dictionary<string, object> GetOrderStatus(string orderId) => new()
    {
        ["order_id"]           = orderId,
        ["status"]             = "shipped",
        ["tracking"]           = "1Z999AA10123456784",
        ["estimated_delivery"] = "2026-02-22",
    };

    [Tool("Retrieve customer details including payment info on file.")]
    public Dictionary<string, object> GetCustomerInfo(string customerId) => new()
    {
        ["customer_id"] = customerId,
        ["name"]        = "Alice Johnson",
        ["email"]       = "alice@example.com",
        ["card_on_file"] = "4532-0150-1234-5678",  // PII — guardrail should catch this
        ["membership"]  = "gold",
    };
}

internal sealed class PiiGuardrails
{
    private static readonly Regex CcPattern  = new(@"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b");
    private static readonly Regex SsnPattern = new(@"\b\d{3}-\d{2}-\d{4}\b");

    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 3)]
    public GuardrailResult NoPii(string content)
    {
        if (CcPattern.IsMatch(content) || SsnPattern.IsMatch(content))
            return new GuardrailResult(false,
                "Your response contains PII (credit card or SSN). " +
                "Redact all card numbers and SSNs before responding.");

        return new GuardrailResult(true);
    }
}
