// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Coding Agent with QA Tester — write, review, and fix code.
//
// Demonstrates swarm orchestration with local code execution:
//   - Coder writes code and executes it, hands off to QA when ready
//   - QA tester reviews, writes tests; transfers back if bugs found
//   - Natural back-and-forth until QA approves
//
// Flow (swarm — LLM-driven handoffs):
//   1. coder writes solution, executes it, transfers to qa_tester
//   2. qa_tester reviews, runs tests — if bugs → transfers back to coder
//   3. coder fixes, re-runs, transfers to qa_tester
//   4. qa_tester verifies → done
//
// Requirements:
//   - Agentspan server with code execution support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── QA Tester ─────────────────────────────────────────────────

var qaTester = new Agent("qa_tester_59")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a meticulous QA engineer. Review code for correctness and bugs. " +
        "Write and execute test cases covering: normal inputs, edge cases, and " +
        "boundary conditions.\n\n" +
        "If you find bugs, describe them clearly and transfer back to coder for fixes. " +
        "If all tests pass, confirm the code is correct and provide your QA report. " +
        "Do NOT transfer back if all tests pass.",
    LocalCodeExecution   = true,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
};

// ── Coder ─────────────────────────────────────────────────────

var coder = new Agent("coder_59")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are an expert Python developer. Write clean, well-structured " +
        "Python code to solve the given problem. Always execute your code to " +
        "verify it works.\n\n" +
        "Once your code runs successfully, transfer to qa_tester for review. " +
        "If the qa_tester reports bugs, fix them, re-run, and transfer back " +
        "to qa_tester for verification.",
    LocalCodeExecution = true,
    ThinkingBudgetTokens = 4096,
    MaxTokens            = 16384,
};

// ── Swarm orchestration ───────────────────────────────────────

var swarm = new Agent("coding_swarm_59")
{
    Model    = Settings.LlmModel,
    Strategy = Strategy.Swarm,
    Agents   = [coder, qaTester],
};

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    swarm,
    "Write a Python function that takes a list of integers and returns the " +
    "two numbers that sum to zero. If no such pair exists, raise ValueError.",
    sessionId: Guid.NewGuid().ToString());

result.PrintResult();
