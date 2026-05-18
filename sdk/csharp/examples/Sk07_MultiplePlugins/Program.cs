// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk07 — Pass three distinct plugin classes at once.
//
// Each plugin contributes a separate concern. The bridge flattens them
// into a single tool list on the agent.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using System.Globalization;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk07;

public sealed class MathPlugin
{
    [KernelFunction, Description("Add two integers.")]
    public int Add(int a, int b) => a + b;

    [KernelFunction, Description("Multiply two integers.")]
    public int Multiply(int a, int b) => a * b;
}

public sealed class TimePlugin
{
    [KernelFunction, Description("Today's date in ISO format (yyyy-MM-dd) in UTC.")]
    public string Today() => DateTime.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
}

public sealed class TextPlugin
{
    [KernelFunction, Description("Convert text to upper case.")]
    public string ToUpper([Description("input text")] string text) => text.ToUpperInvariant();
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_multi",
            model:        Settings.LlmModel,
            instructions: "Use the available tools to answer multi-part questions concisely.",
            new MathPlugin(), new TimePlugin(), new TextPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "What is 12 * 7? Also tell me today's date, and uppercase the word 'agentspan'.");
        result.PrintResult();
    }
}
