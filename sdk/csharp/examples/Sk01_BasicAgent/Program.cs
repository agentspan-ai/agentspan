// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

using System.ComponentModel;
using Agentspan;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk01;

/// <summary>
/// Bridge a plain C# class with [KernelFunction] methods into Agentspan.
///
/// No Kernel setup, no SK ChatClient — Agentspan uses the LLM, SK only contributes
/// the function metadata + invocation glue.
/// </summary>
public sealed class CalculatorPlugin
{
    [KernelFunction, Description("Add two integers and return their sum.")]
    public int Add(
        [Description("first number")]  int a,
        [Description("second number")] int b) => a + b;

    [KernelFunction, Description("Multiply two integers.")]
    public int Multiply(int a, int b) => a * b;
}

public static class Program
{
    public static async Task Main()
    {
        var baseUrl = Environment.GetEnvironmentVariable("AGENTSPAN_SERVER_URL") ?? "http://localhost:6767";

        var agent = SemanticKernelAgent.From(
            name:         "sk_calc_agent",
            model:        "openai/gpt-4o-mini",
            instructions: "You are a calculator. Use the tools to answer math questions.",
            new CalculatorPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = baseUrl });
        var result = await runtime.RunAsync(agent, "What is 7 + 8, and then multiply that by 3?");

        result.PrintResult();
    }
}
