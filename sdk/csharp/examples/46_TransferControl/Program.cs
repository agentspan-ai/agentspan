// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Transfer Control — restrict which agents can hand off to which.
//
// AllowedTransitions constrains handoff paths between sub-agents, preventing
// unwanted transfers. A data_collector can only route to analyst; analyst can
// route to summarizer or back to coordinator; summarizer only to coordinator.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Pipeline agents ───────────────────────────────────────────────────

var dataCollector = new Agent("data_collector_46")
{
    Model        = Settings.LlmModel,
    Instructions = "Collect data using collect_data. Then transfer to the analyst.",
    Tools        = ToolRegistry.FromInstance(new DataCollectorTools()),
};

var analyst = new Agent("analyst_46")
{
    Model        = Settings.LlmModel,
    Instructions = "Analyze data using analyze_data. Transfer to summarizer when done.",
    Tools        = ToolRegistry.FromInstance(new AnalystTools()),
};

var summarizer = new Agent("summarizer_46")
{
    Model        = Settings.LlmModel,
    Instructions = "Write a summary using write_summary.",
    Tools        = ToolRegistry.FromInstance(new SummarizerTools()),
};

// ── Coordinator with constrained transitions ──────────────────────────

var coordinator = new Agent("coordinator_46")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You coordinate a data pipeline. Route to data_collector_46 first, " +
        "then analyst_46, then summarizer_46.",
    Agents   = [dataCollector, analyst, summarizer],
    Strategy = Strategy.Handoff,
    AllowedTransitions = new()
    {
        ["data_collector_46"] = ["analyst_46"],
        ["analyst_46"]        = ["summarizer_46", "coordinator_46"],
        ["summarizer_46"]     = ["coordinator_46"],
    },
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    coordinator,
    "Collect data from the sales database, analyze trends, and write a summary.");

result.PrintResult();

// ── Tool classes ──────────────────────────────────────────────────────

internal sealed class DataCollectorTools
{
    [Tool("Collect data from a named source.")]
    public Dictionary<string, object> CollectData(string source)
        => new() { ["source"] = source, ["records"] = 42, ["status"] = "collected" };
}

internal sealed class AnalystTools
{
    [Tool("Analyze a summary of collected data.")]
    public Dictionary<string, object> AnalyzeData(string dataSummary)
        => new() { ["analysis"] = "Trend is upward", ["confidence"] = 0.87 };
}

internal sealed class SummarizerTools
{
    [Tool("Write a summary report from the given findings.")]
    public Dictionary<string, object> WriteSummary(string findings)
        => new() { ["summary"] = $"Report: {findings[..Math.Min(100, findings.Length)]}", ["word_count"] = 150 };
}
