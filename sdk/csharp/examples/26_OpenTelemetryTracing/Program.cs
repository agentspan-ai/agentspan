// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenTelemetry Tracing — industry-standard observability for agent runs.
//
// AgentTracing uses System.Diagnostics.ActivitySource (the .NET OTel API).
// Wire it to any OTel exporter via AddSource(AgentTracing.SourceName).
//
// Spans emitted:
//   agent.run       — top-level execution
//   agent.tool_call — each tool invocation
//   agent.handoff   — agent-to-agent transitions
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Diagnostics;
using Agentspan;
using Agentspan.Examples;
using OpenTelemetry;
using OpenTelemetry.Trace;

// ── Configure OTel provider ───────────────────────────────────────────

Console.WriteLine($"OpenTelemetry source: {AgentTracing.SourceName}");

using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource(AgentTracing.SourceName)
    .AddConsoleExporter()
    .Build();

Console.WriteLine($"Tracing enabled: {AgentTracing.IsTracingEnabled()}");

// ── Agent with a lookup tool ──────────────────────────────────────────

var agent = new Agent("traced_agent")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new LookupTool()),
    Instructions = "You are a helpful assistant. Use the lookup tool when needed.",
};

// ── Run with a manual trace span wrapping the agent call ─────────────

await using var runtime = new AgentRuntime();

using (var span = AgentTracing.StartAgentRun("traced_agent", "Who created Python?", model: Settings.LlmModel))
{
    var result = await runtime.RunAsync(agent, "Who created Python?");

    if (span is not null && result.TokenUsage is not null)
    {
        AgentTracing.RecordTokenUsage(span,
            promptTokens:     result.TokenUsage.PromptTokens,
            completionTokens: result.TokenUsage.CompletionTokens,
            totalTokens:      result.TokenUsage.TotalTokens);
        span.SetTag("agent.output_length", result.Output?.ToString()?.Length ?? 0);
        span.SetStatus(ActivityStatusCode.Ok);
    }

    result.PrintResult();

    if (result.TokenUsage is not null)
        Console.WriteLine($"Tokens: {result.TokenUsage.TotalTokens}");
}

// ── Tool implementation ───────────────────────────────────────────────

internal sealed class LookupTool
{
    [Tool("Look up information about a topic.")]
    public string Lookup(string query)
    {
        using var span = AgentTracing.StartToolCall("traced_agent", "lookup", $"{{\"query\":\"{query}\"}}");
        var answer = $"Result for '{query}': Python was created by Guido van Rossum in 1991.";
        span?.SetStatus(ActivityStatusCode.Ok);
        return answer;
    }
}
