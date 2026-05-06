// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Nested Strategies — parallel agents inside a sequential pipeline.
//
// Demonstrates composing strategies: a Parallel phase runs multiple
// research agents concurrently, followed by a sequential summarizer.
//
//   pipeline = parallel_research >> summarizer
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Parallel research phase ───────────────────────────────────

var marketAnalyst = new Agent("market_analyst_52")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a market analyst. Analyze the market size, growth rate, " +
        "and key players for the given topic. Be concise (3-4 bullet points).",
};

var riskAnalyst = new Agent("risk_analyst_52")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a risk analyst. Identify the top 3 risks: regulatory, " +
        "technical, and competitive. Be concise.",
};

// Both analysts run concurrently
var parallelResearch = new Agent("research_phase_52")
{
    Agents   = [marketAnalyst, riskAnalyst],
    Strategy = Strategy.Parallel,
};

// ── Sequential summarizer ─────────────────────────────────────

var summarizer = new Agent("summarizer_52")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are an executive briefing writer. Synthesize the market analysis " +
        "and risk assessment into a concise executive summary (1 paragraph).",
};

// ── Pipeline: parallel research → summary ─────────────────────

var pipeline = parallelResearch >> summarizer;

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    pipeline,
    "Launching an AI-powered healthcare diagnostics tool in the US");

result.PrintResult();
