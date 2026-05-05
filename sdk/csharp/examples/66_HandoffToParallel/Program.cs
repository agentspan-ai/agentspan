// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Handoff to Parallel — delegate to a multi-agent group.
//
// Demonstrates a parent agent that can hand off to either a single agent
// (for quick checks) or a parallel multi-agent group (for deep analysis).
//
// Architecture:
//   coordinator (HANDOFF)
//   ├── quick_check           (single agent, fast)
//   └── deep_analysis         (PARALLEL group)
//       ├── market_analyst_66
//       └── risk_analyst_66
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Quick check (single agent) ────────────────────────────────

var quickCheck = new Agent("quick_check_66")
{
    Model        = Settings.LlmModel,
    Instructions = "You provide quick, 1-sentence assessments. Be brief and direct.",
};

// ── Deep analysis (parallel group) ────────────────────────────

var deepAnalysis = new Agent("deep_analysis_66")
{
    Agents = [
        new Agent("market_analyst_66")
        {
            Model        = Settings.LlmModel,
            Instructions = "You analyze market opportunities in 3 bullet points.",
        },
        new Agent("risk_analyst_66")
        {
            Model        = Settings.LlmModel,
            Instructions = "You identify the top 3 risks: regulatory, technical, competitive.",
        },
    ],
    Strategy = Strategy.Parallel,
};

// ── Coordinator with handoff ───────────────────────────────────

var coordinator = new Agent("coordinator_66")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a coordinator. For simple yes/no questions, transfer to quick_check_66. " +
        "For complex strategic questions, transfer to deep_analysis_66 for thorough analysis.",
    Agents   = [quickCheck, deepAnalysis],
    Strategy = Strategy.Handoff,
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Quick Check ---");
var result1 = await runtime.RunAsync(
    coordinator,
    "Is the stock market open today?");
result1.PrintResult();

Console.WriteLine("\n--- Deep Analysis ---");
var result2 = await runtime.RunAsync(
    coordinator,
    "Should we enter the AI healthcare diagnostics market in Europe?");
result2.PrintResult();
