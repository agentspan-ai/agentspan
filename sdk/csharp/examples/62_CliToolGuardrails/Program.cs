// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// CLI Tool with Guardrails — safe command execution.
//
// Demonstrates tool-level guardrails on CLI commands. The agent can run
// whitelisted commands, but a RegexGuardrail blocks dangerous patterns
// (e.g. "rm -rf", "sudo") before the command executes.
//
// If a guardrail fails:
//   - OnFail.Raise — terminates the workflow immediately (hard block)
//   - OnFail.Retry — feeds the rejection back to the LLM for another try
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Guardrails ────────────────────────────────────────────────────────

var blockDestructive = RegexGuardrail.Create(
    patterns:  [@"rm\s+-rf\s+/", @"mkfs\.", @"\bdd\s+if="],
    mode:      "block",
    name:      "block_destructive",
    message:   "Destructive system commands are not allowed.",
    position:  Position.Input,
    onFail:    OnFail.Raise);

var reviewSudo = RegexGuardrail.Create(
    patterns:   [@"\bsudo\b"],
    mode:       "block",
    name:       "review_sudo",
    message:    "Commands requiring sudo are not permitted. Rewrite without elevated privileges.",
    position:   Position.Input,
    onFail:     OnFail.Retry,
    maxRetries: 2);

// ── CLI tool — local worker process ───────────────────────────────────

var runCommand = CliTool.Create(
    allowedCommands: ["ls", "cat", "df", "du", "git", "ps", "uname", "wc"],
    timeoutSeconds:  15);

// ── Agent ─────────────────────────────────────────────────────────────

var agent = new Agent("ops_agent_62")
{
    Model      = Settings.LlmModel,
    Tools      = [runCommand],
    Guardrails = [blockDestructive, reviewSudo],
    Instructions =
        "You are a DevOps assistant. Use the run_command tool to help " +
        "the user inspect and manage their system. You can list files, " +
        "check disk usage, read logs, and run git commands.\n\n" +
        "IMPORTANT: Never use sudo or destructive commands like rm -rf.",
};

// ── Run ───────────────────────────────────────────────────────────────

const string Prompt = "Show me the disk usage summary and list files in the current directory.";

Console.WriteLine(new string('=', 60));
Console.WriteLine("  CLI Tool with Guardrails");
Console.WriteLine("  Allowed: ls, cat, df, du, git, ps, uname, wc");
Console.WriteLine("  Blocked: rm -rf, sudo, mkfs, dd");
Console.WriteLine(new string('=', 60));
Console.WriteLine($"\nPrompt: {Prompt}\n");

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, Prompt);
result.PrintResult();
