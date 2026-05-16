// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk24 — Planner.
//
// ADK's BuiltInPlanner with ThinkingConfig(thinking_budget=1024) for a
// planning phase.
//
// Note: simplified from Java original — the GoogleADKAgent builder does
// not expose planner config; we encode the planning intent in the
// agent instruction.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("research_writer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a research writer. When given a topic:\n" +
        "1. First produce a brief step-by-step PLAN for the report (act as a planner).\n" +
        "2. Then execute the plan: research the topic thoroughly and write a " +
        "structured report with multiple sections.")
    .Tools(new ResearchWriterTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "Write a brief report on the current state of renewable energy " +
    "and climate change solutions.");
result.PrintResult();

internal sealed class ResearchWriterTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _results = new()
    {
        ["climate change solutions"] = new()
        {
            ["results"] = new List<string>
            {
                "Solar energy costs dropped 89% since 2010",
                "Wind power is now cheapest energy source in many regions",
                "Carbon capture technology advancing rapidly",
            },
        },
        ["renewable energy statistics"] = new()
        {
            ["results"] = new List<string>
            {
                "Renewables account for 30% of global electricity (2023)",
                "Solar capacity grew 50% year-over-year",
                "China leads in renewable energy investment",
            },
        },
    };

    [Tool(Name = "search_web", Description = "Search the web for information.")]
    public Dictionary<string, object> SearchWeb(string query)
    {
        var q = query.ToLowerInvariant();
        foreach (var (k, v) in _results)
        {
            foreach (var word in k.Split(' '))
            {
                if (q.Contains(word))
                {
                    var r = new Dictionary<string, object> { ["query"] = query };
                    foreach (var (kk, vv) in v) r[kk] = vv;
                    return r;
                }
            }
        }
        return new Dictionary<string, object> { ["query"] = query, ["results"] = new List<string> { "No specific results found." } };
    }

    [Tool(Name = "write_section", Description = "Write a section of a report.")]
    public Dictionary<string, object> WriteSection(string title, string content)
        => new() { ["section"] = $"## {title}\n\n{content}" };
}
