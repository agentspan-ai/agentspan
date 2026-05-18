// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi10 — Multi-Model Handoff.
//
// A cheap-and-fast triage agent (primary model) that hands off to two
// specialists running on a more capable secondary model — a doc
// specialist with a doc-search tool and a code specialist with a
// code-generation tool.
//
// Note: simplified from Java original — temperature/max_tokens not
// surfaced on the OpenAIAgent builder yet. Intended settings:
//   - triage:         temperature=0.1
//   - doc_specialist: temperature=0.2, max_tokens=500
//   - code_specialist:temperature=0.3, max_tokens=800
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
//   - AGENT_SECONDARY_LLM_MODEL=openai/gpt-4o (optional; falls back to LlmModel)

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var secondaryModel = Environment.GetEnvironmentVariable("AGENT_SECONDARY_LLM_MODEL")
                     ?? Settings.LlmModel;

var docSpecialist = OpenAIAgent.Builder()
    .Name("doc_specialist")
    .Instructions(
        "You are a documentation specialist. Search the docs and provide " +
        "clear, well-structured answers. Include relevant links and examples.")
    .Model(secondaryModel)
    .Tools(new DocTools())
    .Build();

var codeSpecialist = OpenAIAgent.Builder()
    .Name("code_specialist")
    .Instructions(
        "You are a code example specialist. Generate clean, well-commented " +
        "code samples. Always specify the language and include error handling.")
    .Model(secondaryModel)
    .Tools(new CodeTools())
    .Build();

var triage = OpenAIAgent.Builder()
    .Name("triage")
    .Instructions(
        "You are a documentation triage agent. Determine what the user needs " +
        "and hand off to the appropriate specialist:\n" +
        "- For documentation lookups -> doc_specialist\n" +
        "- For code examples -> code_specialist\n" +
        "Keep your response to one sentence before handing off.")
    .Model(Settings.LlmModel)
    .Handoffs(docSpecialist, codeSpecialist)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(
    triage,
    "I need a Python code example for authenticating with the API.");
result.PrintResult();

internal sealed class DocTools
{
    private static readonly Dictionary<string, string> _docs = new()
    {
        ["authentication"] = "Use OAuth 2.0 with JWT tokens. See /auth/login endpoint.",
        ["rate limiting"]  = "100 requests/minute per API key. 429 status on exceeded.",
        ["pagination"]     = "Use cursor-based pagination with ?cursor=xxx&limit=50.",
        ["webhooks"]       = "POST to /webhooks/register with event types and callback URL.",
    };

    [Tool(Name = "search_docs", Description = "Search the documentation for relevant information.")]
    public string SearchDocs(string query)
    {
        var lower = query.ToLowerInvariant();
        foreach (var (k, v) in _docs)
        {
            if (lower.Contains(k)) return v;
        }
        return "No documentation found. Try rephrasing your query.";
    }
}

internal sealed class CodeTools
{
    [Tool(Name = "generate_code_sample", Description = "Generate a code sample for a given topic.")]
    public string GenerateCodeSample(string language, string topic)
    {
        var key = $"{language.ToLowerInvariant()}|{topic.ToLowerInvariant()}";
        return key switch
        {
            "python|authentication" =>
                "import requests\n" +
                "resp = requests.post('/auth/login', json={'key': 'API_KEY'})\n" +
                "token = resp.json()['token']",
            "javascript|authentication" =>
                "const resp = await fetch('/auth/login', {\n" +
                "  method: 'POST',\n" +
                "  body: JSON.stringify({ key: 'API_KEY' })\n" +
                "});\n" +
                "const { token } = await resp.json();",
            _ => $"// Sample for {topic} in {language}\n// (template not available)",
        };
    }
}
