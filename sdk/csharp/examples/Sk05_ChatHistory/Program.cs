// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk05 — Multi-turn conversation with an SK-bridged agent.
//
// Two sequential RunAsync calls show that each turn is independent unless
// the prior context is folded into the prompt. The second turn explicitly
// references the first answer.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk05;

public sealed class GeoPlugin
{
    [KernelFunction, Description("Return the capital of a country.")]
    public string Capital([Description("country name")] string country) =>
        country.ToLowerInvariant() switch
        {
            "france"        => "Paris",
            "japan"         => "Tokyo",
            "australia"     => "Canberra",
            "united states" or "usa" or "us" => "Washington, D.C.",
            _               => "unknown",
        };
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_geo",
            model:        Settings.LlmModel,
            instructions: "Answer geography questions. Use the capital tool when needed.",
            new GeoPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });

        Console.WriteLine("── Turn 1 ──");
        var first = await runtime.RunAsync(agent, "What is the capital of Japan?");
        first.PrintResult();

        Console.WriteLine("\n── Turn 2 (history folded into prompt) ──");
        var priorAnswer = first.Output?.TryGetValue("result", out var v) == true ? v?.ToString() : "(unknown)";
        var followUp = $"Previously you told me the capital of Japan was '{priorAnswer}'. " +
                       "What is the capital of France, and is it further from Tokyo or from London?";
        var second = await runtime.RunAsync(agent, followUp);
        second.PrintResult();
    }
}
