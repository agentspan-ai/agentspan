// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Constrained Speaker Transitions — control which agents can follow which.
//
// AllowedTransitions restricts which agent can speak after which.
// Enforces a code review workflow:
//   developer → reviewer (code must be reviewed)
//   reviewer  → developer OR approver
//   approver  → developer (request revisions)
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Code review team ─────────────────────────────────────────────────

var developer = new Agent("developer")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a software developer. Write or revise code based on feedback. " +
        "Keep responses focused on code changes.",
};

var reviewer = new Agent("reviewer")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a code reviewer. Review the developer's code for bugs, style, " +
        "and best practices. Provide specific, actionable feedback.",
};

var approver = new Agent("approver")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are the tech lead. Review the code and feedback. Either approve " +
        "the code or request revisions with specific guidance.",
};

// Constrained transitions enforce the review protocol
var codeReview = new Agent("code_review")
{
    Model    = Settings.LlmModel,
    Agents   = [developer, reviewer, approver],
    Strategy = Strategy.RoundRobin,
    MaxTurns = 6,
    AllowedTransitions = new Dictionary<string, List<string>>
    {
        ["developer"] = ["reviewer"],
        ["reviewer"]  = ["developer", "approver"],
        ["approver"]  = ["developer"],
    },
};

// ── Run ─────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    codeReview,
    "Write a C# method to validate email addresses using regex.");

result.PrintResult();
