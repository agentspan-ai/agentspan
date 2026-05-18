// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk10 — Pass a KernelPlugin instance instead of a plain object.
//
// Same plugin class as Sk01, but wrapped via KernelPluginFactory.CreateFromObject
// before being handed to SemanticKernelAgent.From. The bridge handles both
// shapes identically.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk10;

public sealed class CalculatorPlugin
{
    [KernelFunction, Description("Add two integers.")]
    public int Add(int a, int b) => a + b;

    [KernelFunction, Description("Subtract b from a.")]
    public int Subtract(int a, int b) => a - b;
}

public static class Program
{
    public static async Task Main()
    {
        KernelPlugin plugin = KernelPluginFactory.CreateFromObject(new CalculatorPlugin(), "calc");

        var agent = SemanticKernelAgent.From(
            name:         "sk_kernelplugin",
            model:        Settings.LlmModel,
            instructions: "Solve arithmetic using the calc plugin.",
            plugin);

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(agent, "Compute (12 + 30) - 7.");
        result.PrintResult();
    }
}
