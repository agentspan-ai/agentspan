// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Fix Guardrail — auto-correct output instead of retrying.
//
// OnFail.Fix: when the guardrail fails, it provides a FixedOutput that
// replaces the LLM response directly without calling the LLM again.
//
// Useful when the correction is deterministic (stripping PII, truncating,
// formatting) — faster and cheaper than retry.
//
// OnFail modes:
//   Retry  — send feedback to LLM and regenerate (best for style issues)
//   Fix    — replace output with FixedOutput (best for deterministic fixes)
//   Raise  — terminate the workflow with an error
//   Human  — pause for human review
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.RegularExpressions;
using Agentspan;
using Agentspan.Examples;

// ── Fix guardrail: redact phone numbers ───────────────────────────────

var guardrailDefs = GuardrailRegistry.FromInstance(new PhoneRedactor());
var agent = new Agent("directory_agent")
{
    Model        = Settings.LlmModel,
    Tools        = ToolRegistry.FromInstance(new ContactDirectory()),
    Instructions =
        "You are a company directory assistant. When asked about employees, " +
        "look up their contact info and share everything you find.",
    Guardrails   = guardrailDefs,
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine("=" + new string('=', 59));
Console.WriteLine("  Scenario 1: Contact with phone number (guardrail triggers)");
Console.WriteLine("=" + new string('=', 59));
var r1 = await runtime.RunAsync(agent, "What's Alice Johnson's contact information?");
r1.PrintResult();

var out1 = r1.Output?.GetValueOrDefault("result")?.ToString() ?? "";
if (out1.Contains("(555) 123-4567") || out1.Contains("555-123-4567"))
    Console.WriteLine("[FAIL] Phone number leaked through the guardrail!");
else if (out1.Contains("[PHONE REDACTED]"))
    Console.WriteLine("[OK] Phone number was auto-redacted by fix guardrail");
else
    Console.WriteLine("[INFO] Phone number not visible in output");

Console.WriteLine("\n" + "=" + new string('=', 59));
Console.WriteLine("  Scenario 2: Contact without phone (guardrail passes)");
Console.WriteLine("=" + new string('=', 59));
var r2 = await runtime.RunAsync(agent, "What's Charlie's email?");
r2.PrintResult();

// ── Tool ──────────────────────────────────────────────────────────────

internal sealed class ContactDirectory
{
    private static readonly Dictionary<string, Dictionary<string, string>> Contacts = new()
    {
        ["alice"] = new() { ["name"] = "Alice Johnson", ["email"] = "alice@example.com", ["phone"] = "(555) 123-4567", ["department"] = "Engineering" },
        ["bob"]   = new() { ["name"] = "Bob Smith",     ["email"] = "bob@example.com",   ["phone"] = "555-987-6543",    ["department"] = "Marketing"   },
        ["charlie"] = new() { ["name"] = "Charlie Davis", ["email"] = "charlie@example.com", ["department"] = "Design" },
    };

    [Tool("Look up contact information for an employee.")]
    public Dictionary<string, object> GetContactInfo(string name)
    {
        var key = name.ToLowerInvariant().Split(' ')[0];
        if (Contacts.TryGetValue(key, out var c))
            return c.ToDictionary(kv => kv.Key, kv => (object)kv.Value);
        return new() { ["error"] = $"No contact found for '{name}'" };
    }
}

// ── Fix guardrail ────────────────────────────────────────────────────

internal sealed class PhoneRedactor
{
    private static readonly Regex PhonePattern = new(
        @"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        RegexOptions.Compiled);

    [Guardrail("phone_redactor", OnFail = OnFail.Fix, Position = Position.Output)]
    public GuardrailResult RedactPhoneNumbers(string content)
    {
        if (!PhonePattern.IsMatch(content))
            return new GuardrailResult(true);

        var redacted = PhonePattern.Replace(content, "[PHONE REDACTED]");
        return new GuardrailResult(false, "Phone numbers detected and redacted.", redacted);
    }
}
