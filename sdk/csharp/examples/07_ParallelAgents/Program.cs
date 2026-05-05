// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Parallel Agents — fan-out / fan-in.
//
// Demonstrates the PARALLEL strategy where all sub-agents run concurrently
// on the same input and their results are aggregated.
//
// Architecture:
//   analysis (PARALLEL)
//   ├── market_analyst   — market size, trends, opportunities
//   ├── risk_analyst     — regulatory, technical, competitive risks
//   └── compliance       — data privacy, regulations, standards
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional)

using Agentspan;
using Agentspan.Examples;

// ── Specialist analysts ─────────────────────────────────────────────

var marketAnalyst = new Agent("market_analyst")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are a market analyst. Analyze the given topic from a market perspective: " +
        "market size, growth trends, key players, and opportunities.",
};

var riskAnalyst = new Agent("risk_analyst")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are a risk analyst. Analyze the given topic for risks: " +
        "regulatory risks, technical risks, competitive threats, and mitigation strategies.",
};

var complianceChecker = new Agent("compliance")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are a compliance specialist. Check the given topic for compliance considerations: " +
        "data privacy, regulatory requirements, and industry standards.",
};

// ── Parallel analysis coordinator ───────────────────────────────────

var analysis = new Agent("analysis")
{
    Model = Settings.LlmModel,
    Agents = [marketAnalyst, riskAnalyst, complianceChecker],
    Strategy = Strategy.Parallel,
};

// ── Run ─────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    analysis,
    "Launching an AI-powered healthcare diagnostic tool in the US market");
result.PrintResult();
