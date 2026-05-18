// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// OpenAi08 — Agent as Tool (manager pattern).
//
// A manager agent that delegates to two specialist sub-agents
// (sentiment analyzer + keyword extractor) to produce a unified
// text analysis summary.
//
// Note: simplified from Java original — Python's Agent.as_tool() has
// no direct OpenAIAgent equivalent yet, so specialists are wired as
// .Handoffs(...). The LLM still routes to the right specialist, but
// control is handed off rather than retained by the manager.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.OpenAI;

var sentimentAgent = OpenAIAgent.Builder()
    .Name("sentiment_analyzer")
    .Instructions(
        "You analyze text sentiment. Use the analyze_sentiment tool and " +
        "provide a brief interpretation.")
    .Model(Settings.LlmModel)
    .Tools(new SentimentTools())
    .Build();

var keywordAgent = OpenAIAgent.Builder()
    .Name("keyword_extractor")
    .Instructions(
        "You extract keywords from text. Use the extract_keywords tool and " +
        "categorize the results.")
    .Model(Settings.LlmModel)
    .Tools(new KeywordTools())
    .Build();

var manager = OpenAIAgent.Builder()
    .Name("text_analysis_manager")
    .Instructions(
        "You are a text analysis manager. When given text to analyze:\n" +
        "1. Use the sentiment analyzer to understand the tone\n" +
        "2. Use the keyword extractor to identify key topics\n" +
        "3. Synthesize the results into a concise summary\n\n" +
        "Always use both tools before providing your summary.")
    .Model(Settings.LlmModel)
    .Handoffs(sentimentAgent, keywordAgent)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(
    manager,
    "Analyze this review: 'The new laptop is excellent! The display is amazing " +
    "and the battery life is wonderful. However, the keyboard feels terrible " +
    "and the trackpad is the worst I've used.'");
result.PrintResult();

internal sealed class SentimentTools
{
    private static readonly HashSet<string> Positive = new(StringComparer.OrdinalIgnoreCase)
        { "great", "love", "excellent", "amazing", "wonderful", "best" };
    private static readonly HashSet<string> Negative = new(StringComparer.OrdinalIgnoreCase)
        { "bad", "terrible", "hate", "awful", "worst", "horrible" };

    [Tool(Name = "analyze_sentiment",
        Description = "Analyze the sentiment of text. Returns positive, negative, or neutral.")]
    public string AnalyzeSentiment(string text)
    {
        var words = new HashSet<string>(text.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries));
        var p = words.Count(w => Positive.Contains(w));
        var n = words.Count(w => Negative.Contains(w));
        var total = p + n;
        if (p > n) return $"Positive sentiment (score: {p}/{total})";
        if (n > p) return $"Negative sentiment (score: {n}/{total})";
        return "Neutral sentiment";
    }
}

internal sealed class KeywordTools
{
    private static readonly HashSet<string> StopWords = new(StringComparer.OrdinalIgnoreCase)
    {
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
        "to", "for", "of", "and", "or", "but", "with", "this", "that", "i",
    };

    [Tool(Name = "extract_keywords", Description = "Extract key topics and keywords from text.")]
    public string ExtractKeywords(string text)
    {
        var tokens = text.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var ordered = new List<string>();
        var seen = new HashSet<string>();
        foreach (var raw in tokens)
        {
            var w = new string(raw.Where(c => c != '.' && c != ',' && c != '!' && c != '?').ToArray());
            if (w.Length > 3 && !StopWords.Contains(w) && seen.Add(w))
            {
                ordered.Add(w);
                if (ordered.Count >= 10) break;
            }
        }
        return "Keywords: " + string.Join(", ", ordered);
    }
}
