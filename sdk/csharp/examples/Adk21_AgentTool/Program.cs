// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk21 — Agent Tool.
//
// Wrapping agents as callable tools via AgentTool.Create(). Unlike
// sub-agents (handoff), an agent_tool runs inline and returns its output
// back to the parent like a function call.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var researcher = GoogleADKAgent.Builder()
    .Name("researcher")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a research assistant. Use the knowledge base tool to find " +
        "information and provide concise, factual answers.")
    .Tools(new ResearcherTools())
    .Build();

var calculator = GoogleADKAgent.Builder()
    .Name("calculator")
    .Model(Settings.LlmModel)
    .Instruction("You are a math assistant. Use the compute tool for calculations.")
    .Tools(new CalculatorTools())
    .Build();

var manager = GoogleADKAgent.Builder()
    .Name("manager")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a manager agent. You have two specialist agents available as tools:\n" +
        "- researcher: for looking up information\n" +
        "- calculator: for math computations\n\n" +
        "Use the appropriate agent tool to answer the user's question. " +
        "You can call multiple agent tools if needed.")
    .ToolDefs(new[] { AgentTool.Create(researcher), AgentTool.Create(calculator) })
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(manager,
    "Look up information about Python and Rust, then calculate " +
    "what percentage of Python's 4 key use cases overlap with Rust's 4 use cases.");
result.PrintResult();

internal sealed class ResearcherTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _data = new()
    {
        ["python"] = new()
        {
            ["summary"]       = "Python is a high-level programming language created by Guido van Rossum in 1991.",
            ["popularity"]    = "Most popular language on TIOBE index (2024)",
            ["key_use_cases"] = new List<string> { "web development", "data science", "AI/ML", "automation" },
        },
        ["rust"] = new()
        {
            ["summary"]       = "Rust is a systems programming language focused on safety and performance.",
            ["popularity"]    = "Most admired language on Stack Overflow survey (2024)",
            ["key_use_cases"] = new List<string> { "systems programming", "WebAssembly", "CLI tools", "embedded" },
        },
    };

    [Tool(Name = "search_knowledge_base", Description = "Search an internal knowledge base for information.")]
    public Dictionary<string, object> SearchKnowledgeBase(string query)
    {
        var q = query.ToLowerInvariant();
        foreach (var (k, v) in _data)
        {
            if (q.Contains(k))
            {
                var r = new Dictionary<string, object> { ["query"] = query, ["found"] = true };
                foreach (var (kk, vv) in v) r[kk] = vv;
                return r;
            }
        }
        return new Dictionary<string, object> { ["query"] = query, ["found"] = false, ["summary"] = "No results found." };
    }
}

internal sealed class CalculatorTools
{
    [Tool(Name = "compute", Description = "Evaluate a mathematical expression.")]
    public Dictionary<string, object> Compute(string expression)
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
