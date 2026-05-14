// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk12 — Code review helper.
//
// A plugin runs lightweight static checks on a C# snippet (long lines,
// TODO markers, console writes). The agent assembles a review report.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk12;

public sealed class CodeReviewPlugin
{
    [KernelFunction, Description("Count lines in a code snippet that exceed the given width.")]
    public int CountLongLines(
        [Description("code snippet")] string code,
        [Description("max acceptable line length")] int maxWidth = 100)
        => code.Split('\n').Count(l => l.TrimEnd().Length > maxWidth);

    [KernelFunction, Description("Return all TODO / FIXME comments found in the snippet, one per line.")]
    public string FindTodos([Description("code snippet")] string code)
    {
        var hits = code.Split('\n')
            .Where(l => l.Contains("TODO", StringComparison.OrdinalIgnoreCase)
                     || l.Contains("FIXME", StringComparison.OrdinalIgnoreCase))
            .Select(l => l.Trim());
        var joined = string.Join("\n", hits);
        return string.IsNullOrEmpty(joined) ? "none" : joined;
    }

    [KernelFunction, Description("Count Console.WriteLine calls — flagging stray debug output.")]
    public int CountConsoleWrites([Description("code snippet")] string code)
        => code.Split("Console.WriteLine").Length - 1;
}

public static class Program
{
    public static async Task Main()
    {
        const string snippet = """
            // TODO: extract helper
            void Process(IEnumerable<string> items) {
                Console.WriteLine("processing");
                foreach (var item in items) { var trimmed = item.Trim(); /* FIXME: handle nulls */ Console.WriteLine(trimmed); }
            }
            """;

        var agent = SemanticKernelAgent.From(
            name:         "sk_code_review",
            model:        Settings.LlmModel,
            instructions: "Run all available checks on the snippet and write a short review summary.",
            new CodeReviewPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            $"Review this code snippet and list issues:\n```\n{snippet}\n```");
        result.PrintResult();
    }
}
