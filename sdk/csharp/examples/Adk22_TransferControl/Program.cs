// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk22 — Transfer Control.
//
// Restricted agent handoffs. Python uses disallow_transfer_to_parent /
// disallow_transfer_to_peers on LlmAgent.
//
// Note: simplified from Java original — the GoogleADKAgent builder does
// not expose those flags directly; the role-based intent is documented
// in each agent's instruction.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var specialistA = GoogleADKAgent.Builder()
    .Name("data_collector")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a data collection specialist. Gather relevant data points " +
        "about the topic and pass them to the analyst for analysis. " +
        "You should NOT return to the coordinator directly.")
    .Build();

var specialistB = GoogleADKAgent.Builder()
    .Name("analyst")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a data analyst. Take the data collected and provide " +
        "a concise analysis with insights. You can transfer to any agent.")
    .Build();

var specialistC = GoogleADKAgent.Builder()
    .Name("summarizer")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a summarizer. Take the analysis and create a brief " +
        "executive summary. Return the summary to the coordinator. " +
        "Do NOT transfer to other specialists.")
    .Build();

var coordinator = GoogleADKAgent.Builder()
    .Name("research_coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a research coordinator managing a team of specialists:\n" +
        "- data_collector: gathers raw data (cannot return to you directly)\n" +
        "- analyst: analyzes data (can transfer freely)\n" +
        "- summarizer: creates executive summaries (cannot transfer to peers)\n\n" +
        "Route the user's request through the appropriate workflow.")
    .SubAgents(specialistA, specialistB, specialistC)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "Research the current state of renewable energy adoption worldwide.");
result.PrintResult();
