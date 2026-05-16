// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Agent Tool — wrap an agent as a callable tool.
//
// Unlike sub-agents (which use handoff delegation), an AgentTool is called
// inline by the parent LLM like a function call. The child agent runs its
// own workflow and returns the result as a tool output.
//
//   manager (parent)
//     tools:
//       - AgentTool.Create(researcher)  ← child agent with search tool
//       - calculate                     ← regular tool
//
// Requirements:
//   - Agentspan server with AgentTool support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Child agent with its own search tool ──────────────────────────────

var researcher = new Agent("researcher_45")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a research assistant. Use search_knowledge_base to find " +
        "information about topics. Provide concise summaries.",
    Tools = ToolRegistry.FromInstance(new KnowledgeBaseTools()),
};

// ── Parent agent that uses researcher as an inline tool ───────────────

var manager = new Agent("manager_45")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a project manager. Use the researcher tool to gather " +
        "information and the calculate tool for math. Synthesize findings.",
    Tools =
    [
        // Wrap researcher agent as a callable tool
        AgentTool.Create(researcher),
        // Regular inline tool
        .. ToolRegistry.FromInstance(new CalculatorTools()),
    ],
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    manager,
    "Research Python and Rust, then calculate how many use cases they have combined.");

result.PrintResult();

// ── Tool implementations ──────────────────────────────────────────────

internal sealed class KnowledgeBaseTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> Data = new()
    {
        ["python"] = new()
        {
            ["summary"]   = "Python is a high-level programming language.",
            ["use_cases"] = new[] { "web development", "data science", "automation" },
        },
        ["rust"] = new()
        {
            ["summary"]   = "Rust is a systems language focused on safety and performance.",
            ["use_cases"] = new[] { "systems programming", "WebAssembly", "CLI tools" },
        },
    };

    [Tool("Search an internal knowledge base for information about a topic.")]
    public Dictionary<string, object> SearchKnowledgeBase(string query)
    {
        foreach (var (key, val) in Data)
        {
            if (query.Contains(key, StringComparison.OrdinalIgnoreCase))
                return new Dictionary<string, object>(val) { ["query"] = query };
        }
        return new() { ["query"] = query, ["summary"] = "No specific data found." };
    }
}

internal sealed class CalculatorTools
{
    [Tool("Evaluate a simple math expression (+, -, *, /).")]
    public Dictionary<string, object> Calculate(string expression)
    {
        // Simple expression evaluator (no ^, no functions)
        try
        {
            var result = new System.Data.DataTable().Compute(expression, null);
            return new() { ["result"] = result };
        }
        catch (Exception ex)
        {
            return new() { ["error"] = ex.Message };
        }
    }
}
