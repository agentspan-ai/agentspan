// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Standalone Guardrails — use guardrail functions as plain validators.
//
// In C#, guardrail logic is plain classes or methods. Part 1 shows
// calling guardrail checks directly in-process (no server needed).
// Part 2 shows running the same checks as server-side guardrail workers
// attached to an agent.
//
// Requirements:
//   Part 1 (standalone): no server needed.
//   Part 2 (as agent guardrails):
//     - Agentspan server with LLM support
//     - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//     - AGENTSPAN_LLM_MODEL set in environment

using System.Text.RegularExpressions;
using Agentspan;
using Agentspan.Examples;

// ── Guardrail definitions ─────────────────────────────────────────────

// Each "guardrail" is a function: string → (bool passed, string? message)
static (bool Passed, string? Message) NoPii(string content)
{
    var cc  = new Regex(@"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b");
    var ssn = new Regex(@"\b\d{3}-\d{2}-\d{4}\b");
    if (cc.IsMatch(content) || ssn.IsMatch(content))
        return (false, "Contains PII (credit card or SSN).");
    return (true, null);
}

static (bool Passed, string? Message) NoProfanity(string content)
{
    var banned = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "damn", "hell", "crap" };
    var words  = content.Split(' ', StringSplitOptions.RemoveEmptyEntries);
    var found  = words.Where(w => banned.Contains(w.Trim('?', '!', '.', ','))).ToList();
    if (found.Count > 0)
        return (false, $"Profanity detected: {string.Join(", ", found)}");
    return (true, null);
}

static (bool Passed, string? Message) WordLimit(string content)
{
    var count = content.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length;
    if (count > 100)
        return (false, $"Too long ({count} words). Limit is 100.");
    return (true, null);
}

// ── Part 1: Standalone — validate text directly, no server needed ─────

static bool Validate(string text, IEnumerable<(string Name, Func<string, (bool, string?)> Check)> checks)
{
    bool allPassed = true;
    foreach (var (name, check) in checks)
    {
        var (passed, message) = check(text);
        Console.WriteLine(passed ? $"  [PASS] {name}" : $"  [FAIL] {name}: {message}");
        if (!passed) allPassed = false;
    }
    return allPassed;
}

var guardrails = new[]
{
    ("NoPii",        (Func<string, (bool, string?)>)NoPii),
    ("NoProfanity",  (Func<string, (bool, string?)>)NoProfanity),
    ("WordLimit",    (Func<string, (bool, string?)>)WordLimit),
};

Console.WriteLine("============================================================");
Console.WriteLine("Part 1: Standalone guardrails (no server)");
Console.WriteLine("============================================================");

Console.WriteLine("\nTest 1 — clean text:");
var t1 = "Hello, your order #1234 has shipped and will arrive Friday.";
Console.WriteLine($"  Result: {(Validate(t1, guardrails) ? "PASSED" : "BLOCKED")}\n");

Console.WriteLine("Test 2 — contains credit card number:");
var t2 = "Your card on file is 4532-0150-1234-5678. Order confirmed.";
Console.WriteLine($"  Result: {(Validate(t2, guardrails) ? "PASSED" : "BLOCKED")}\n");

Console.WriteLine("Test 3 — contains profanity:");
var t3 = "What the hell happened to my order?";
Console.WriteLine($"  Result: {(Validate(t3, guardrails) ? "PASSED" : "BLOCKED")}\n");

Console.WriteLine("Test 4 — exceeds word limit:");
var t4 = string.Join(" ", Enumerable.Repeat("word", 150));
Console.WriteLine($"  Result: {(Validate(t4, guardrails) ? "PASSED" : "BLOCKED")}\n");

// ── Part 2: As server-side agent guardrails ───────────────────────────

if (args.Contains("--agent"))
{
    Console.WriteLine("------------------------------------------------------------");
    Console.WriteLine("Part 2: Guardrail workers attached to an agent");
    Console.WriteLine("------------------------------------------------------------\n");

    var piiGuard = RegexGuardrail.Create(
        patterns:  [@"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", @"\b\d{3}-\d{2}-\d{4}\b"],
        mode:      "block",
        name:      "no_pii",
        message:   "Contains PII (credit card or SSN).",
        position:  Position.Output,
        onFail:    OnFail.Retry,
        maxRetries: 2);

    var agent = new Agent("support_agent")
    {
        Model        = Settings.LlmModel,
        Instructions = "You are a support agent. Never include credit card numbers in responses.",
        Guardrails   = [piiGuard],
    };

    await using var runtime = new AgentRuntime();
    var result = await runtime.RunAsync(agent, "Summarize today's support tickets.");
    result.PrintResult();
}
else
{
    Console.WriteLine("------------------------------------------------------------");
    Console.WriteLine("To also run guardrails as agent guardrail workers:");
    Console.WriteLine("  dotnet run -- --agent");
}
