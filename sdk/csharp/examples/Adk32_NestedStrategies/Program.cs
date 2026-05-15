// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk32 — Nested Strategies.
//
// Composing agent strategies — Python uses SequentialAgent containing a
// ParallelAgent research phase followed by a summarizer. The
// GoogleADKAgent encodes the same intent via nested sub-agent groupings.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var marketAnalyst = GoogleADKAgent.Builder()
    .Name("market_analyst")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a market analyst. Analyze the market size, growth rate, " +
        "and key players for the given topic. Be concise (3-4 bullet points).")
    .Build();

var riskAnalyst = GoogleADKAgent.Builder()
    .Name("risk_analyst")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a risk analyst. Identify the top 3 risks: regulatory, " +
        "technical, and competitive. Be concise.")
    .Build();

var parallelResearch = GoogleADKAgent.Builder()
    .Name("research_phase")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate a parallel research phase. Dispatch the topic to " +
        "market_analyst and risk_analyst concurrently, then aggregate their outputs.")
    .SubAgents(marketAnalyst, riskAnalyst)
    .Build();

var summarizer = GoogleADKAgent.Builder()
    .Name("summarizer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are an executive briefing writer. Synthesize the market analysis " +
        "and risk assessment into a concise executive summary (1 paragraph).")
    .Build();

var pipeline = GoogleADKAgent.Builder()
    .Name("analysis_pipeline")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate an analysis pipeline. First run research_phase " +
        "(parallel research), then summarizer.")
    .SubAgents(parallelResearch, summarizer)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(pipeline,
    "Launching an AI-powered healthcare diagnostics tool in the US");
result.PrintResult();
