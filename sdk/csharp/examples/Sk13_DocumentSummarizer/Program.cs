// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk13 — Document analyzer plugin.
//
// Tools count words, count sentences, and extract the most frequent
// non-stopword. The agent uses them to deliver a brief summary.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk13;

public sealed class DocumentPlugin
{
    private static readonly HashSet<string> Stopwords = new(StringComparer.OrdinalIgnoreCase)
    {
        "the","a","an","of","and","or","is","are","to","in","on","for","with","by","as","at","it","this","that","be","was","were","but","from","its"
    };

    [KernelFunction, Description("Count words in a document.")]
    public int WordCount([Description("document text")] string text)
        => text.Split(new[] { ' ', '\n', '\t' }, StringSplitOptions.RemoveEmptyEntries).Length;

    [KernelFunction, Description("Count sentences (defined by . ! ?) in a document.")]
    public int SentenceCount([Description("document text")] string text)
        => text.Split(new[] { '.', '!', '?' }, StringSplitOptions.RemoveEmptyEntries).Length;

    [KernelFunction, Description("Return the most frequent non-stopword in the document.")]
    public string TopKeyword([Description("document text")] string text)
    {
        var tokens = text.ToLowerInvariant()
            .Split(new[] { ' ', '\n', '\t', '.', ',', '!', '?' }, StringSplitOptions.RemoveEmptyEntries)
            .Where(t => !Stopwords.Contains(t));
        var grouped = tokens.GroupBy(t => t).OrderByDescending(g => g.Count()).FirstOrDefault();
        return grouped?.Key ?? "(none)";
    }
}

public static class Program
{
    public static async Task Main()
    {
        const string doc = """
            Agentspan is a runtime for AI agents. Agentspan compiles agent definitions
            into deterministic workflows. The Agentspan server orchestrates agents across
            languages — Python, TypeScript, Java, C#. Agents call tools, tools return data,
            and the runtime persists every step.
            """;

        var agent = SemanticKernelAgent.From(
            name:         "sk_doc_summary",
            model:        Settings.LlmModel,
            instructions: "Use the analyzer tools to produce a one-paragraph summary including counts and the top keyword.",
            new DocumentPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            $"Analyze this document and summarize it:\n{doc}");
        result.PrintResult();
    }
}
