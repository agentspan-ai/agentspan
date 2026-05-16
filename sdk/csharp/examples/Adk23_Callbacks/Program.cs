// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk23 — Callbacks (lifecycle hooks).
//
// Lifecycle hooks (before/after_model_callback) — exposed here as
// regular tools that mirror the Python signatures.
//
// Note: simplified from Java original — the GoogleADKAgent builder
// does not expose model callback wiring directly; we expose the
// callback payloads as ordinary tools.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("monitored_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a helpful assistant. Answer questions concisely. " +
        "Keep responses under 200 words.")
    .Tools(new Callbacks())
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(agent,
    "Explain the difference between supervised and unsupervised machine learning.");
result.PrintResult();

internal sealed class Callbacks
{
    [Tool(Name = "log_before_model",
        Description = "Called before each LLM invocation. Returns empty dict to continue normally.")]
    public Dictionary<string, object> LogBeforeModel(string callback_position, string agent_name)
    {
        Console.WriteLine($"[CALLBACK] Before model call for agent '{agent_name}'");
        return new Dictionary<string, object>();
    }

    [Tool(Name = "inspect_after_model",
        Description = "Called after each LLM invocation. Inspects the response.")]
    public Dictionary<string, object> InspectAfterModel(string callback_position, string agent_name, string llm_result)
    {
        var wordCount = string.IsNullOrEmpty(llm_result)
            ? 0
            : llm_result.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length;
        Console.WriteLine($"[CALLBACK] After model call for '{agent_name}': {wordCount} words generated");
        if (wordCount > 500)
            Console.WriteLine($"[CALLBACK] Warning: Response exceeds 500 words ({wordCount})");
        return new Dictionary<string, object>();
    }
}
