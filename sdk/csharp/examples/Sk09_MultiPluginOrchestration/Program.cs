// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk09 — Three-stage orchestration via multiple SK plugins.
//
// research → outline → polish, each backed by a separate plugin.
// The agent decides the order based on the user request.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk09;

public sealed class ResearchPlugin
{
    [KernelFunction, Description("Look up 3 fast facts about a topic. Returns a single string of comma-separated facts.")]
    public string LookupFacts([Description("topic to research")] string topic) =>
        topic.ToLowerInvariant() switch
        {
            "ada lovelace" => "born 1815, daughter of Lord Byron, wrote first published algorithm for Babbage's engine",
            "moon"         => "average distance 384400km, no atmosphere, tidally locked to Earth",
            _              => $"no facts on hand for '{topic}'",
        };
}

public sealed class OutlinePlugin
{
    [KernelFunction, Description("Turn a fact string into a 3-bullet outline.")]
    public string Outline([Description("facts string from LookupFacts")] string facts)
        => string.Join("\n", facts.Split(',').Select(f => "- " + f.Trim()));
}

public sealed class PolishPlugin
{
    [KernelFunction, Description("Apply tone polish to a draft. Tone may be 'casual' or 'formal'.")]
    public string Polish(
        [Description("draft text")] string draft,
        [Description("'casual' or 'formal'")] string tone)
        => tone.Equals("casual", StringComparison.OrdinalIgnoreCase)
            ? $"hey — quick rundown:\n{draft}"
            : $"Brief overview:\n{draft}";
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_orchestrator",
            model:        Settings.LlmModel,
            instructions: "When asked to write a brief, call lookup_facts → outline → polish in order.",
            new ResearchPlugin(), new OutlinePlugin(), new PolishPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "Write me a casual brief about Ada Lovelace.");
        result.PrintResult();
    }
}
