// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk30 — Thinking Config.
//
// ADK's extended thinking mode via ThinkingConfig(thinking_budget=2048).
//
// Note: simplified from Java original — the GoogleADKAgent builder does
// not expose thinking_config directly; we encode the step-by-step
// reasoning intent in the agent instruction.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("deep_thinker")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are an analytical assistant. Think carefully through complex " +
        "problems step by step. Use the calculate tool for math.")
    .Tools(new CalcTools())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "If a train travels 120 km in 2 hours, then speeds up by 50% for " +
    "the next 3 hours, what is the total distance traveled?");
result.PrintResult();

internal sealed class CalcTools
{
    [Tool(Name = "calculate", Description = "Evaluate a mathematical expression.")]
    public Dictionary<string, object> Calculate(string expression)
    {
        if (!System.Text.RegularExpressions.Regex.IsMatch(expression, @"^[0-9+\-*/().\s]+$"))
            return new Dictionary<string, object> { ["expression"] = expression, ["error"] = "Invalid expression" };
        try
        {
            var pos = new int[] { 0 };
            var s = System.Text.RegularExpressions.Regex.Replace(expression, @"\s+", "");
            var result = EvalExpr(s, pos);
            return new Dictionary<string, object> { ["expression"] = expression, ["result"] = result };
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object> { ["expression"] = expression, ["error"] = ex.Message };
        }
    }

    private static double EvalExpr(string s, int[] pos)
    {
        var val = EvalTerm(s, pos);
        while (pos[0] < s.Length && (s[pos[0]] == '+' || s[pos[0]] == '-'))
        {
            var op = s[pos[0]++];
            val = op == '+' ? val + EvalTerm(s, pos) : val - EvalTerm(s, pos);
        }
        return val;
    }
    private static double EvalTerm(string s, int[] pos)
    {
        var val = EvalFactor(s, pos);
        while (pos[0] < s.Length && (s[pos[0]] == '*' || s[pos[0]] == '/'))
        {
            var op = s[pos[0]++];
            val = op == '*' ? val * EvalFactor(s, pos) : val / EvalFactor(s, pos);
        }
        return val;
    }
    private static double EvalFactor(string s, int[] pos)
    {
        if (pos[0] < s.Length && s[pos[0]] == '(')
        {
            pos[0]++;
            var val = EvalExpr(s, pos);
            pos[0]++;
            return val;
        }
        var start = pos[0];
        while (pos[0] < s.Length && (char.IsDigit(s[pos[0]]) || s[pos[0]] == '.')) pos[0]++;
        return double.Parse(s[start..pos[0]]);
    }
}
