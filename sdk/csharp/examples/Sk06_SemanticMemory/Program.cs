// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk06 — In-memory "semantic memory" plugin.
//
// A plugin exposes Remember and Recall functions backed by a process-local
// dictionary. The LLM uses Remember to stash facts and Recall to retrieve
// them. State lives in the plugin instance, so the same agent instance
// shares memory across turns within one process.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.Collections.Concurrent;
using System.ComponentModel;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk06;

public sealed class MemoryPlugin
{
    private readonly ConcurrentDictionary<string, string> _store = new();

    [KernelFunction, Description("Remember a value under a key.")]
    public string Remember(
        [Description("key to store under")] string key,
        [Description("value to remember")]  string value)
    {
        _store[key] = value;
        return $"stored '{key}'";
    }

    [KernelFunction, Description("Recall a previously remembered value by key. Returns 'NOT_FOUND' if absent.")]
    public string Recall([Description("key to look up")] string key)
        => _store.TryGetValue(key, out var v) ? v : "NOT_FOUND";
}

public static class Program
{
    public static async Task Main()
    {
        var memory = new MemoryPlugin();
        var agent = SemanticKernelAgent.From(
            name:         "sk_memory",
            model:        Settings.LlmModel,
            instructions: "Use remember/recall tools to track user-provided facts across the conversation.",
            memory);

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });

        var r1 = await runtime.RunAsync(agent,
            "Remember that my favorite color is teal and my favorite number is 17.");
        r1.PrintResult();

        var r2 = await runtime.RunAsync(agent,
            "What is my favorite color, and what is my favorite number?");
        r2.PrintResult();
    }
}
