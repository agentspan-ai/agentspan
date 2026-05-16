// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk15 — Research assistant with a stub "search" backend.
//
// The plugin returns canned arxiv-style results plus a save_note function.
// The agent searches, picks two hits, and saves a synthesised note.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk15;

public sealed class ResearchPlugin
{
    private readonly List<string> _notes = new();

    [KernelFunction, Description("Search a stub arxiv index. Returns up to 3 titles, one per line.")]
    public string Search([Description("query terms")] string query) =>
        query.ToLowerInvariant() switch
        {
            var q when q.Contains("transformer") =>
                "Attention Is All You Need (Vaswani et al., 2017)\nLongformer: The Long-Document Transformer (Beltagy et al., 2020)\nReformer: The Efficient Transformer (Kitaev et al., 2020)",
            var q when q.Contains("retrieval") =>
                "Dense Passage Retrieval (Karpukhin et al., 2020)\nREALM: Retrieval-Augmented Language Model Pre-Training (Guu et al., 2020)",
            _ => "no results",
        };

    [KernelFunction, Description("Save a research note. Returns the saved note count.")]
    public int SaveNote([Description("note text")] string text)
    {
        _notes.Add(text);
        return _notes.Count;
    }
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_research",
            model:        Settings.LlmModel,
            instructions: "Search the index, pick the two most relevant papers, and save a short synthesis note via save_note.",
            new ResearchPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "Find foundational papers about the transformer architecture and save a brief note covering them.");
        result.PrintResult();
    }
}
