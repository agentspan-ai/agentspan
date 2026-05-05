// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Composable Termination — AND/OR rules for stopping agents.
//
// Combines termination conditions using & (AND) and | (OR) operators:
//   - TextMentionTermination: stop when output contains specific text
//   - StopMessageTermination: stop on exact match
//   - MaxMessageTermination: stop after N messages
//   - TokenUsageTermination: stop when token budget exceeded
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

await using var runtime = new AgentRuntime();

// ── Example 1: Simple text mention ───────────────────────────────────

var agent1 = new Agent("researcher")
{
    Model        = Settings.LlmModel,
    Instructions = "Research the topic and say DONE when you have enough info.",
    Termination  = new TextMentionTermination("DONE"),
};

Console.WriteLine("--- Simple text mention termination ---");
var result1 = await runtime.RunAsync(agent1, "What are AI agents?");
result1.PrintResult();
