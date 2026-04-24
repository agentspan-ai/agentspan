// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Human Guardrail — pause for human review when output fails policy.
//
// OnFail.Human triggers a WAITING event in the stream when the guardrail
// detects flagged content. The human can then approve, reject, or edit
// the response before it's returned to the caller.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Compliance guardrail using regex ─────────────────────────────────

var flaggedTerms = new[] { "investment advice", "guaranteed returns", "risk-free" };
var complianceGuard = RegexGuardrail.Create(
    patterns:   flaggedTerms,
    mode:       "block",
    name:       "compliance",
    message:    "Response contains flagged financial term. Needs human review.",
    position:   Position.Output,
    onFail:     OnFail.Human,
    maxRetries: 1);

// ── Agent ─────────────────────────────────────────────────────────────

var agent = new Agent("finance_agent")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new MarketTools()),
    Instructions =
        "You are a financial information assistant. Provide market data " +
        "and general financial information. You may discuss investment " +
        "strategies and returns.",
    Guardrails = [complianceGuard],
};

// ── Stream with human review on WAITING ──────────────────────────────

await using var runtime = new AgentRuntime();
var handle = await runtime.StartAsync(
    agent,
    "Look up AAPL and explain whether it's a good investment. " +
    "Include your opinion on potential returns.");

Console.WriteLine($"Started: {handle.ExecutionId}\n");

await foreach (var ev in handle.StreamAsync())
{
    switch (ev.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {ev.Content}");
            break;

        case EventType.ToolCall:
            Console.WriteLine($"  [tool_call] {ev.ToolName}({ev.Args})");
            break;

        case EventType.ToolResult:
            Console.WriteLine($"  [tool_result] {ev.ToolName} -> {ev.Result}");
            break;

        case EventType.Waiting:
            Console.WriteLine("\n--- Human review required ---");
            Console.Write("  Approve this response? (y/n): ");
            var approved = Console.ReadLine()?.Trim().ToLower() is "y" or "yes";
            if (approved)
            {
                await handle.ApproveAsync();
                Console.WriteLine("  Approved.\n");
            }
            else
            {
                await handle.RejectAsync("Rejected by compliance officer.");
                Console.WriteLine("  Rejected.\n");
            }
            break;

        case EventType.Done:
            Console.WriteLine($"\nDone: {ev.Content ?? ev.Status}");
            break;

        case EventType.Error:
            Console.WriteLine($"\nError: {ev.Content}");
            break;
    }
}

// ── Market data tool ──────────────────────────────────────────────────

internal sealed class MarketTools
{
    [Tool("Get current market data for a stock ticker.")]
    public Dictionary<string, object> GetMarketData(string ticker) => new()
    {
        ["ticker"] = ticker,
        ["price"]  = 185.42,
        ["change"] = "+2.3%",
        ["volume"] = "45.2M",
    };
}
