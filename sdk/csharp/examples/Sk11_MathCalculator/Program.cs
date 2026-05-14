// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk11 — Rich math calculator plugin.
//
// Add, subtract, multiply, divide, power, sqrt — each as a separate
// [KernelFunction]. The agent composes them to evaluate an expression.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk11;

public sealed class MathCalculatorPlugin
{
    [KernelFunction, Description("Add two numbers.")]
    public double Add(double a, double b) => a + b;

    [KernelFunction, Description("Subtract b from a.")]
    public double Subtract(double a, double b) => a - b;

    [KernelFunction, Description("Multiply two numbers.")]
    public double Multiply(double a, double b) => a * b;

    [KernelFunction, Description("Divide a by b. Throws on division by zero.")]
    public double Divide(double a, double b)
    {
        if (b == 0) throw new DivideByZeroException();
        return a / b;
    }

    [KernelFunction, Description("Raise base to the given exponent.")]
    public double Power(
        [Description("base")] double @base,
        [Description("exponent")] double exponent) => Math.Pow(@base, exponent);

    [KernelFunction, Description("Square root of a non-negative number.")]
    public double Sqrt([Description("non-negative value")] double value)
    {
        if (value < 0) throw new ArgumentOutOfRangeException(nameof(value));
        return Math.Sqrt(value);
    }
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_math_calc",
            model:        Settings.LlmModel,
            instructions: "Evaluate arithmetic by calling the math tools step by step.",
            new MathCalculatorPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "Compute sqrt(144) + 3^4, then divide that by 2.");
        result.PrintResult();
    }
}
