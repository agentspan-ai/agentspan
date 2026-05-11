// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Local Code Execution — agents that write and run code.
//
// Demonstrates three ways to enable code execution on an agent:
//
//   1. Simple flag: LocalCodeExecution = true
//   2. With restrictions: AllowedLanguages + AllowedCommands on Agent
//   3. Full config: CodeExecution = new CodeExecutionConfig(...)
//
// When LocalCodeExecution=true, the agent automatically gets an
// execute_code tool. The LLM calls it via native function calling.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Example 1: Simple flag ────────────────────────────────────
// Just flip LocalCodeExecution = true — defaults to Python, no restrictions.

var simpleCoder = new Agent("simple_coder_39")
{
    Model                = Settings.LlmModel,
    LocalCodeExecution   = true,
    Instructions         = "You are a Python developer. Write and execute code to solve problems.",
};

// ── Example 2: With restrictions ──────────────────────────────
// Allow Python + Bash, but only permit pip and ls commands.

var restrictedCoder = new Agent("restricted_coder_39")
{
    Model              = Settings.LlmModel,
    LocalCodeExecution = true,
    AllowedLanguages   = ["python", "bash"],
    AllowedCommands    = ["pip", "ls", "cat", "git"],
    Instructions       =
        "You are a developer with restricted shell access. " +
        "You can write Python and Bash code, but only use " +
        "pip, ls, cat, and git commands.",
};

// ── Example 3: Full CodeExecutionConfig ───────────────────────

var configCoder = new Agent("config_coder_39")
{
    Model      = Settings.LlmModel,
    CodeExecution = new CodeExecutionConfig(
        AllowedLanguages: ["python"],
        AllowedCommands:  ["pip"],
        Timeout:          60),
    Instructions = "You are a Python developer with a 60s timeout and pip access only.",
};

// ── Run example 1 ─────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("--- Simple Code Execution ---");
var result1 = await runtime.RunAsync(
    simpleCoder,
    "Write a Python function to find the first 10 prime numbers and print them.");
result1.PrintResult();

Console.WriteLine("\n--- Restricted Code Execution ---");
var result2 = await runtime.RunAsync(
    restrictedCoder,
    "List the files in the current directory using bash.");
result2.PrintResult();
