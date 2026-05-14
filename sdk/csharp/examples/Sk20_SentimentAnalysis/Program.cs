// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk20 — Sentiment analysis via a simple keyword-rule plugin.
//
// score_sentiment returns +1 / 0 / -1 based on lexicon hits. classify
// returns "positive" / "neutral" / "negative". The agent classifies a
// short list of customer reviews using the tools.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk20;

public sealed class SentimentPlugin
{
    private static readonly string[] Positive = { "great", "love", "excellent", "amazing", "good", "happy", "fast" };
    private static readonly string[] Negative = { "bad",   "hate", "terrible",  "awful",   "slow", "broken", "late" };

    [KernelFunction, Description("Integer sentiment score for the input: +1 positive, 0 neutral, -1 negative.")]
    public int ScoreSentiment([Description("text to score")] string text)
    {
        var t = text.ToLowerInvariant();
        var pos = Positive.Count(w => t.Contains(w));
        var neg = Negative.Count(w => t.Contains(w));
        return Math.Sign(pos - neg);
    }

    [KernelFunction, Description("Classify text as 'positive', 'neutral', or 'negative'.")]
    public string Classify([Description("text to classify")] string text)
        => ScoreSentiment(text) switch
        {
            > 0 => "positive",
            < 0 => "negative",
            _   => "neutral",
        };
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_sentiment",
            model:        Settings.LlmModel,
            instructions: "Classify each review using the tools, then return a one-line summary per review.",
            new SentimentPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            """
            Classify these reviews:
            1) Great product, fast shipping, would buy again.
            2) The package arrived late and the box was broken.
            3) It works. Nothing exciting, nothing terrible.
            """);
        result.PrintResult();
    }
}
