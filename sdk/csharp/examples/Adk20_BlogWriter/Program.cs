// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk20 — Blog Writer.
//
// A sequential content pipeline of sub-agents
// (researcher -> writer -> editor) with output_key state passing.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var researcher = GoogleADKAgent.Builder()
    .Name("blog_researcher")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a research assistant. Use the search tool to gather information " +
        "about the given topic. Present the key findings clearly.")
    .Tools(new ResearchTools())
    .Build();

var writer = GoogleADKAgent.Builder()
    .Name("blog_writer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a blog writer. Based on the research notes provided, " +
        "write a short blog post (3-4 paragraphs). Include a catchy title. " +
        "Incorporate SEO keywords naturally.")
    .Build();

var editor = GoogleADKAgent.Builder()
    .Name("blog_editor")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a blog editor. Review and polish the blog draft. " +
        "Improve clarity, flow, and engagement. Keep the same length. " +
        "Output only the final polished blog post.")
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("content_coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a content coordinator. First use the researcher to gather information, " +
        "then the writer to create a draft, and finally the editor to polish it. " +
        "Present the final blog post to the user.")
    .SubAgents(researcher, writer, editor)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "Write a blog post about the conductor oss workflow and how its the best workflow engine for the agentic era. " +
    "Make sure to write at-least 5000 word and use markdown to format the content");
Console.WriteLine($"Status: {result.Status}");
result.PrintResult();

internal sealed class ResearchTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _topics = new()
    {
        ["ai"] = new()
        {
            ["key_points"] = new List<string>
            {
                "AI adoption grew 72% in enterprises in 2024",
                "Generative AI is transforming content creation and coding",
                "AI safety and regulation are top policy priorities",
            },
            ["sources"] = new List<string> { "TechReview", "AI Journal", "Industry Report 2024" },
        },
        ["sustainability"] = new()
        {
            ["key_points"] = new List<string>
            {
                "Renewable energy hit 30% of global electricity in 2024",
                "Carbon capture technology is scaling rapidly",
                "Green bonds market exceeded $500B",
            },
            ["sources"] = new List<string> { "GreenTech Weekly", "Climate Report", "Energy Journal" },
        },
    };

    [Tool(Name = "search_topic", Description = "Search for information about a topic.")]
    public Dictionary<string, object> SearchTopic(string topic)
    {
        var t = topic.ToLowerInvariant();
        foreach (var (k, v) in _topics)
        {
            if (t.Contains(k))
            {
                var r = new Dictionary<string, object> { ["found"] = true };
                foreach (var (kk, vv) in v) r[kk] = vv;
                return r;
            }
        }
        return new Dictionary<string, object>
        {
            ["found"]      = true,
            ["key_points"] = new List<string> { $"Key insight about {topic}" },
            ["sources"]    = new List<string> { "General Research" },
        };
    }

    [Tool(Name = "check_seo_keywords", Description = "Get SEO keyword suggestions for a topic.")]
    public Dictionary<string, object> CheckSeoKeywords(string topic)
        => new()
        {
            ["primary_keyword"]   = topic.ToLowerInvariant().Replace(" ", "-"),
            ["related_keywords"]  = new List<string> { $"{topic} trends", $"{topic} 2025", $"best {topic} practices" },
            ["search_volume"]     = "high",
        };
}
