// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.Diagnostics;

namespace Agentspan;

/// <summary>
/// OpenTelemetry tracing helpers for agent execution.
///
/// .NET uses <see cref="System.Diagnostics.ActivitySource"/> as its OTel-compatible
/// tracing API. Wire up an OpenTelemetry SDK TracerProvider to export spans:
///
/// <code>
/// using var tracerProvider = Sdk.CreateTracerProviderBuilder()
///     .AddSource(AgentTracing.SourceName)
///     .AddConsoleExporter()
///     .Build();
/// </code>
///
/// Spans emitted:
///   - agent.run      — top-level agent execution
///   - agent.tool_call — tool executions
///   - agent.handoff  — agent-to-agent transitions
/// </summary>
public static class AgentTracing
{
    /// <summary>The <see cref="ActivitySource"/> name used by this SDK. Use this with AddSource().</summary>
    public const string SourceName = "agentspan.agents";

    internal static readonly ActivitySource Source = new(SourceName, "1.0.0");

    /// <summary>Returns true if there is an active OTel listener on this source.</summary>
    public static bool IsTracingEnabled() => Source.HasListeners();

    /// <summary>Start an "agent.run" span. Dispose the returned activity to end it.</summary>
    public static Activity? StartAgentRun(string agentName, string prompt, string model = "", string sessionId = "")
    {
        var activity = Source.StartActivity("agent.run", ActivityKind.Internal);
        if (activity is null) return null;

        activity.SetTag("agent.name", agentName);
        activity.SetTag("agent.prompt_length", prompt.Length);
        if (!string.IsNullOrEmpty(model))     activity.SetTag("agent.model", model);
        if (!string.IsNullOrEmpty(sessionId)) activity.SetTag("agent.session_id", sessionId);
        return activity;
    }

    /// <summary>Start an "agent.tool_call" span.</summary>
    public static Activity? StartToolCall(string agentName, string toolName, string? args = null)
    {
        var activity = Source.StartActivity("agent.tool_call", ActivityKind.Internal);
        if (activity is null) return null;

        activity.SetTag("agent.name", agentName);
        activity.SetTag("tool.name", toolName);
        if (args is not null) activity.SetTag("tool.args", args.Length > 1000 ? args[..1000] : args);
        return activity;
    }

    /// <summary>Start an "agent.handoff" span.</summary>
    public static Activity? StartHandoff(string sourceAgent, string targetAgent)
    {
        var activity = Source.StartActivity("agent.handoff", ActivityKind.Internal);
        if (activity is null) return null;

        activity.SetTag("handoff.source", sourceAgent);
        activity.SetTag("handoff.target", targetAgent);
        return activity;
    }

    /// <summary>Record token usage on an existing span.</summary>
    public static void RecordTokenUsage(Activity? activity, int promptTokens = 0, int completionTokens = 0, int totalTokens = 0)
    {
        if (activity is null) return;
        if (promptTokens    > 0) activity.SetTag("llm.prompt_tokens",      promptTokens);
        if (completionTokens > 0) activity.SetTag("llm.completion_tokens", completionTokens);
        if (totalTokens     > 0) activity.SetTag("llm.total_tokens",       totalTokens);
    }
}
