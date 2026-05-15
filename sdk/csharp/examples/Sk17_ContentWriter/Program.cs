// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk17 — Content writer pipeline.
//
// Plugin functions: pick_angle, suggest_headline, count_words. The agent
// chains them to draft a short blog post intro.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk17;

public sealed class ContentPlugin
{
    [KernelFunction, Description("Suggest a content angle for a topic, biased toward the requested audience.")]
    public string PickAngle(
        [Description("topic")]    string topic,
        [Description("audience")] string audience)
        => $"angle: How '{topic}' affects {audience} day-to-day";

    [KernelFunction, Description("Suggest a headline given an angle.")]
    public string SuggestHeadline([Description("the angle")] string angle)
        => $"5 ways the future is closer than you think — {angle.Replace("angle: ", "")}";

    [KernelFunction, Description("Count words in a draft.")]
    public int CountWords([Description("draft text")] string draft)
        => draft.Split(new[] { ' ', '\n', '\t' }, StringSplitOptions.RemoveEmptyEntries).Length;
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_content_writer",
            model:        Settings.LlmModel,
            instructions: "Call pick_angle then suggest_headline before drafting a 3-sentence intro. Use count_words to confirm length.",
            new ContentPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "Draft a short blog intro about 'agent orchestration' aimed at developers.");
        result.PrintResult();
    }
}
