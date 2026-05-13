// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Random Strategy — random sub-agent selection each turn.
//
// Demonstrates Strategy.Random where a random sub-agent is picked each
// iteration. Unlike RoundRobin (fixed rotation), Random adds variety —
// useful for brainstorming or generating diverse perspectives.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

var creative = new Agent("creative_16r")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a creative thinker. Suggest innovative, unconventional ideas. " +
        "Keep your response to 2-3 sentences.",
};

var practical = new Agent("practical_16r")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a practical thinker. Focus on feasibility and cost-effectiveness. " +
        "Keep your response to 2-3 sentences.",
};

var critical = new Agent("critical_16r")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a critical thinker. Identify risks and potential issues. " +
        "Keep your response to 2-3 sentences.",
};

// Random selection: each turn, one of the three agents is picked at random
var brainstorm = new Agent("brainstorm_16r")
{
    Model    = Settings.LlmModel,
    Agents   = [creative, practical, critical],
    Strategy = Strategy.Random,
    MaxTurns = 6,
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    brainstorm,
    "How should we approach building an AI-powered customer service platform?");
result.PrintResult();
