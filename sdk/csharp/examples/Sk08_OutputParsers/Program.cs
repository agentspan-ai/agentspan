// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk08 — Rich typed parameters: int, double, bool, optional.
//
// Exercises the bridge's JSON Schema derivation: each parameter type
// becomes a typed slot in the tool spec the LLM sees.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk08;

public sealed class GeometryPlugin
{
    [KernelFunction, Description("Compute the area of a rectangle.")]
    public double RectangleArea(
        [Description("width in metres")]  double width,
        [Description("height in metres")] double height) => width * height;

    [KernelFunction, Description("Compute the perimeter of a rectangle. Set 'metric' to true for metres, false for feet (conversion 3.28084).")]
    public double RectanglePerimeter(
        [Description("width")]  double width,
        [Description("height")] double height,
        [Description("true = metric, false = imperial")] bool metric = true)
    {
        var p = 2 * (width + height);
        return metric ? p : p * 3.28084;
    }

    [KernelFunction, Description("Compute n!. Refuses negative input.")]
    public long Factorial([Description("non-negative integer")] int n)
    {
        if (n < 0) throw new ArgumentOutOfRangeException(nameof(n));
        long acc = 1;
        for (int i = 2; i <= n; i++) acc *= i;
        return acc;
    }
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_geom",
            model:        Settings.LlmModel,
            instructions: "Call the geometry tools with the right types and report results to 2 decimals where applicable.",
            new GeometryPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "What is the area of a 4.5 m x 7.2 m room, its perimeter in feet, and what is 6 factorial?");
        result.PrintResult();
    }
}
