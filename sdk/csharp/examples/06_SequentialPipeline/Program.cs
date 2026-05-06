// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sequential Pipeline — Agent >> Agent >> Agent.
//
// Demonstrates the sequential strategy where agents run in order and the
// output of each agent becomes the input of the next.
//
// Also shows the >> operator shorthand.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional)

using Agentspan;
using Agentspan.Examples;

// ── Pipeline agents ─────────────────────────────────────────────────

var researcher = new Agent("researcher")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are a researcher. Given a topic, provide key facts and data points. " +
        "Be thorough but concise. Output raw research findings.",
};

var writer = new Agent("writer")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are a writer. Take research findings and write a clear, engaging " +
        "article. Use headers and bullet points where appropriate.",
};

var editor = new Agent("editor")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are an editor. Review the article for clarity, grammar, and tone. " +
        "Make improvements and output the final polished version.",
};

// ── Build pipeline with >> operator ────────────────────────────────
// researcher >> writer produces a sequential wrapper agent,
// then >> editor appends editor to its sub-agents list.

var pipeline = researcher >> writer >> editor;

// ── Run ─────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(pipeline, "The impact of AI agents on software development in 2025");
result.PrintResult();

// Option 2: Using Strategy parameter (equivalent)
// var pipeline = new Agent("content_pipeline")
// {
//     Model = Settings.LlmModel,
//     Agents = [researcher, writer, editor],
//     Strategy = Strategy.Sequential,
// };
