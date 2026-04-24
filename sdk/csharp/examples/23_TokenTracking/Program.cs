// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Token & Cost Tracking — monitor LLM token usage per agent run.
//
// AgentResult.TokenUsage provides aggregated token usage across all
// LLM calls in an agent execution (prompt, completion, total).
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

var agent = new Agent("math_tutor")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new MathTools()),
    Instructions =
        "You are a math tutor. Solve problems step by step, using the calculate " +
        "tool for computations. Explain each step clearly.",
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    agent,
    "Calculate the compound interest on $10,000 at 5% annual rate " +
    "compounded monthly for 3 years.");

result.PrintResult();

// Token usage is extracted from the execution record
if (result.TokenUsage is not null)
{
    Console.WriteLine("Token Usage Summary:");
    Console.WriteLine($"  Prompt tokens:     {result.TokenUsage.PromptTokens}");
    Console.WriteLine($"  Completion tokens: {result.TokenUsage.CompletionTokens}");
    Console.WriteLine($"  Total tokens:      {result.TokenUsage.TotalTokens}");

    // Estimate cost (example pricing — adjust for your model)
    var promptCost     = result.TokenUsage.PromptTokens     * 0.0025 / 1000;
    var completionCost = result.TokenUsage.CompletionTokens * 0.010  / 1000;
    Console.WriteLine($"\n  Estimated cost: ${promptCost + completionCost:F4}");
}
else
{
    Console.WriteLine("(Token usage not available from workflow)");
}

// ── Math tool ────────────────────────────────────────────────────────

internal sealed class MathTools
{
    [Tool("Evaluate a mathematical expression. Supports +, -, *, /, ^ (power), and parentheses.")]
    public string Calculate(string expression)
    {
        try
        {
            // Normalize: replace ^ with ** for parsing then evaluate via DataTable
            // DataTable doesn't support ^ but we can use a simple recursive descent parser.
            var result = Evaluate(expression.Trim());
            return result.ToString("G10");
        }
        catch (Exception ex)
        {
            return $"Error: {ex.Message}";
        }
    }

    private static double Evaluate(string expr)
    {
        // Remove spaces
        expr = expr.Replace(" ", "");
        int pos = 0;
        return ParseAddSub(expr, ref pos);
    }

    private static double ParseAddSub(string expr, ref int pos)
    {
        double left = ParseMulDiv(expr, ref pos);
        while (pos < expr.Length && (expr[pos] == '+' || expr[pos] == '-'))
        {
            var op = expr[pos++];
            double right = ParseMulDiv(expr, ref pos);
            left = op == '+' ? left + right : left - right;
        }
        return left;
    }

    private static double ParseMulDiv(string expr, ref int pos)
    {
        double left = ParsePow(expr, ref pos);
        while (pos < expr.Length && (expr[pos] == '*' || expr[pos] == '/'))
        {
            var op = expr[pos++];
            double right = ParsePow(expr, ref pos);
            left = op == '*' ? left * right : left / right;
        }
        return left;
    }

    private static double ParsePow(string expr, ref int pos)
    {
        double base_ = ParseUnary(expr, ref pos);
        if (pos < expr.Length && expr[pos] == '^')
        {
            pos++;
            double exp = ParseUnary(expr, ref pos);
            return Math.Pow(base_, exp);
        }
        return base_;
    }

    private static double ParseUnary(string expr, ref int pos)
    {
        if (pos < expr.Length && expr[pos] == '-') { pos++; return -ParsePrimary(expr, ref pos); }
        if (pos < expr.Length && expr[pos] == '+') { pos++; }
        return ParsePrimary(expr, ref pos);
    }

    private static double ParsePrimary(string expr, ref int pos)
    {
        if (pos < expr.Length && expr[pos] == '(')
        {
            pos++; // skip '('
            double val = ParseAddSub(expr, ref pos);
            if (pos < expr.Length && expr[pos] == ')') pos++;
            return val;
        }
        int start = pos;
        while (pos < expr.Length && (char.IsDigit(expr[pos]) || expr[pos] == '.'))
            pos++;
        return double.Parse(expr[start..pos]);
    }
}
