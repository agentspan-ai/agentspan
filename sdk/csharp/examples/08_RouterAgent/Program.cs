// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Router Agent — LLM-based routing to specialists.
//
// Demonstrates the ROUTER strategy where a dedicated router/classifier agent
// decides which specialist sub-agent handles each request.
//
// Architecture:
//   team (ROUTER, router=selector)
//   ├── planner   — design/architecture tasks
//   ├── coder     — implementation tasks
//   └── reviewer  — code review tasks
//
// The selector is a separate agent whose only job is routing.
// It is NOT one of the specialist agents.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment (optional)

using Agentspan;
using Agentspan.Examples;

// ── Specialist agents ───────────────────────────────────────────────

var planner = new Agent("planner")
{
    Model = Settings.LlmModel,
    Instructions = "You create implementation plans. Break down tasks into clear numbered steps.",
};

var coder = new Agent("coder")
{
    Model = Settings.LlmModel,
    Instructions = "You write code. Output clean, well-documented C# code.",
};

var reviewer = new Agent("reviewer")
{
    Model = Settings.LlmModel,
    Instructions = "You review code. Check for bugs, style issues, and suggest improvements.",
};

// ── Dedicated router/classifier (separate from specialists) ─────────

var selector = new Agent("dev_team_selector")
{
    Model = Settings.LlmModel,
    Instructions =
        "You are a request classifier. Select the right specialist:\n" +
        "- planner: for design, architecture, or planning tasks\n" +
        "- coder: for writing or implementing code\n" +
        "- reviewer: for reviewing, auditing, or improving existing code",
};

// ── Router team ─────────────────────────────────────────────────────

var team = new Agent("dev_team")
{
    Model = Settings.LlmModel,
    Agents = [planner, coder, reviewer],
    Strategy = Strategy.Router,
    Router = selector, // dedicated classifier — not one of the specialists
};

// ── Run ─────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    team,
    "Write a C# method to validate email addresses using regex");
result.PrintResult();
