// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Router to Sequential — route to a pipeline sub-agent.
//
// Demonstrates a router that selects between a single agent (for quick
// answers) and a sequential pipeline (for research tasks).
//
// Architecture:
//   team (ROUTER, router=selector)
//   ├── quick_answer_67       (single agent)
//   └── research_pipeline_67  (SEQUENTIAL)
//       ├── researcher_67
//       └── writer_67
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Quick answer ──────────────────────────────────────────────

var quickAnswer = new Agent("quick_answer_67")
{
    Model        = Settings.LlmModel,
    Instructions = "You give quick, 1-2 sentence answers to simple questions.",
};

// ── Research pipeline ─────────────────────────────────────────

var researchPipeline = new Agent("research_pipeline_67")
{
    Model    = Settings.LlmModel,
    Agents   = [
        new Agent("researcher_67")
        {
            Model        = Settings.LlmModel,
            Instructions = "You are a researcher. Research the topic and provide 3-5 key facts with supporting details.",
        },
        new Agent("writer_67")
        {
            Model        = Settings.LlmModel,
            Instructions = "You are a writer. Take the research findings and write a clear, engaging summary. Use headers and bullet points.",
        },
    ],
    Strategy = Strategy.Sequential,
};

// ── Router ────────────────────────────────────────────────────

var selector = new Agent("selector_67")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a request classifier. Select the right team member:\n" +
        "- quick_answer_67: for simple factual questions with short answers\n" +
        "- research_pipeline_67: for research tasks requiring analysis and writing",
};

var team = new Agent("team_67")
{
    Model    = Settings.LlmModel,
    Router   = selector,
    Agents   = [quickAnswer, researchPipeline],
    Strategy = Strategy.Router,
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Quick Question ---");
var result1 = await runtime.RunAsync(team, "What is the capital of France?");
result1.PrintResult();

Console.WriteLine("\n--- Research Question ---");
var result2 = await runtime.RunAsync(
    team,
    "Research the impact of AI on software engineering jobs over the next decade.");
result2.PrintResult();
