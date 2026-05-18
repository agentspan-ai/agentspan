// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk07 — Output Key State.
//
// ADK's output_key for passing data between sub-agents through shared
// session state.
//
// Note: simplified from Java original — the GoogleADKAgent builder does
// not expose output_key directly; the structural pattern (coordinator
// -> analyst + visualizer) is preserved via SubAgents.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var analyst = GoogleADKAgent.Builder()
    .Name("data_analyst")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a data analyst. Use the analyze_data tool to examine datasets. " +
        "Provide a clear summary of the key findings.")
    .Tools(new AnalystTools())
    .Build();

var visualizer = GoogleADKAgent.Builder()
    .Name("chart_designer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a data visualization expert. Based on the analysis results, " +
        "suggest appropriate visualizations. Use the generate_chart_description " +
        "tool for each key metric.")
    .Tools(new VisualizerTools())
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("report_coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a report coordinator. First, have the data analyst examine " +
        "the requested dataset. Then, have the chart designer suggest " +
        "visualizations. Provide a final executive summary.")
    .SubAgents(analyst, visualizer)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "Create a report on the sales_q4 dataset with visualization recommendations.");
result.PrintResult();

internal sealed class AnalystTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _datasets = new(StringComparer.OrdinalIgnoreCase)
    {
        ["sales_q4"] = new()
        {
            ["total_revenue"]   = "$2.3M",
            ["growth_rate"]     = "12%",
            ["top_product"]     = "Widget Pro",
            ["avg_order_value"] = "$156",
        },
        ["user_engagement"] = new()
        {
            ["daily_active_users"]   = "45,000",
            ["avg_session_duration"] = "8.5 min",
            ["retention_rate"]       = "72%",
            ["churn_rate"]           = "5.2%",
        },
    };

    [Tool(Name = "analyze_data", Description = "Analyze a dataset and return key statistics.")]
    public Dictionary<string, object> AnalyzeData(string dataset)
    {
        return _datasets.TryGetValue(dataset, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"Dataset '{dataset}' not found" };
    }
}

internal sealed class VisualizerTools
{
    [Tool(Name = "generate_chart_description", Description = "Generate a description for a chart visualization.")]
    public Dictionary<string, object> GenerateChartDescription(string metric, string value)
    {
        return new Dictionary<string, object>
        {
            ["chart_type"]     = value.Contains('%') ? "gauge" : "bar",
            ["metric"]         = metric,
            ["value"]          = value,
            ["recommendation"] = $"Track {metric} weekly for trend analysis.",
        };
    }
}
