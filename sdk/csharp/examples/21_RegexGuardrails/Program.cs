// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Regex Guardrails — pattern-based content validation.
//
// RegexGuardrail.Create() builds a guardrail from regex patterns:
//   - Block mode (default): reject responses containing matches
//   - Allow mode: require responses to match at least one pattern
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// ── Block mode: reject responses with PII ────────────────────────────

var noEmails = RegexGuardrail.Create(
    pattern:   @"[\w.+\-]+@[\w\-]+\.[\w.\-]+",
    mode:      "block",
    name:      "no_email_addresses",
    message:   "Response must not contain email addresses. Redact them.",
    position:  Position.Output,
    onFail:    OnFail.Retry,
    maxRetries: 3);

var noSsn = RegexGuardrail.Create(
    pattern:   @"\b\d{3}-\d{2}-\d{4}\b",
    mode:      "block",
    name:      "no_ssn",
    message:   "Response must not contain Social Security Numbers.",
    position:  Position.Output,
    onFail:    OnFail.Raise,
    maxRetries: 3);

// ── Tool that returns PII ─────────────────────────────────────────────

var tools = ToolRegistry.FromInstance(new HrTools());

// ── Agent with PII-blocking guardrails ───────────────────────────────

var agent = new Agent("hr_assistant")
{
    Model        = Settings.LlmModel,
    Tools        = tools,
    Instructions =
        "You are an HR assistant. When asked about employees, look up their " +
        "profile and share ALL the details you find.",
    Guardrails = [noEmails, noSsn],
};

// ── Run ───────────────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();

Console.WriteLine(new string('=', 60));
Console.WriteLine("  Scenario 1: Request PII — guardrails trigger");
Console.WriteLine(new string('=', 60));

var result1 = await runtime.RunAsync(agent, "Tell me everything about user U-001.");
result1.PrintResult();

var output1 = result1.Output?.ToString() ?? "";
Console.WriteLine(output1.Contains("alice.johnson@example.com")
    ? "[FAIL] Email leaked!"
    : "[OK] Email was blocked by RegexGuardrail");

Console.WriteLine();
Console.WriteLine(new string('=', 60));
Console.WriteLine("  Scenario 2: Non-PII question — guardrails pass");
Console.WriteLine(new string('=', 60));

var cleanAgent = new Agent("dept_assistant")
{
    Model        = Settings.LlmModel,
    Instructions = "You are an HR assistant. Answer questions about departments.",
    Guardrails   = [noEmails, noSsn],
};

var result2 = await runtime.RunAsync(cleanAgent, "What departments exist at the company?");
result2.PrintResult();

// ── HR tool implementation ────────────────────────────────────────────

internal sealed class HrTools
{
    [Tool("Retrieve a user's profile from the database.")]
    public Dictionary<string, object> GetUserProfile(string userId) =>
        new()
        {
            ["name"]       = "Alice Johnson",
            ["email"]      = "alice.johnson@example.com",  // PII - should be blocked
            ["ssn"]        = "123-45-6789",                // PII - should be blocked
            ["department"] = "Engineering",
            ["role"]       = "Senior Developer",
        };
}
