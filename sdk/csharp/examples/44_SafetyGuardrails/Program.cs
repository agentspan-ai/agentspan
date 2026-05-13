// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Safety Guardrails Pipeline — PII detection and sanitization.
//
// A sequential pipeline scans the primary agent's output for PII:
//   assistant >> safety_checker
//
// - assistant: A helpful agent that answers questions (may include PII).
// - safety_checker: Detects PII with regex tools and sanitizes any matches.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.RegularExpressions;
using Agentspan;
using Agentspan.Examples;

// ── Primary assistant ─────────────────────────────────────────

var assistant = new Agent("helpful_assistant_44")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a helpful customer service assistant. Answer questions " +
        "about account details, contact information, and general inquiries. " +
        "When providing information, include relevant details.",
};

// ── Safety checker ────────────────────────────────────────────

var safetyChecker = new Agent("safety_checker_44")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a safety reviewer. Check the previous agent's response " +
        "for any PII (emails, phone numbers, SSNs, credit card numbers). " +
        "Use check_pii on the response text. If PII is found, use " +
        "sanitize_response to clean it. Output only the sanitized version.",
    Tools = ToolRegistry.FromInstance(new SafetyTools()),
};

// ── Pipeline ──────────────────────────────────────────────────

var pipeline = assistant >> safetyChecker;

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    pipeline,
    "What are the contact details for our support team? " +
    "Include email support@company.com and phone 555-123-4567.");

result.PrintResult();

// ── Tool class ────────────────────────────────────────────────

internal sealed partial class SafetyTools
{
    [GeneratedRegex(@"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")]
    private static partial Regex EmailRegex();
    [GeneratedRegex(@"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")]
    private static partial Regex PhoneRegex();
    [GeneratedRegex(@"\b\d{3}-\d{2}-\d{4}\b")]
    private static partial Regex SsnRegex();
    [GeneratedRegex(@"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")]
    private static partial Regex CardRegex();

    [Tool("Check text for personally identifiable information (PII).")]
    public Dictionary<string, object> CheckPii(string text)
    {
        var found = new Dictionary<string, int>();
        if (EmailRegex().IsMatch(text)) found["email"]       = EmailRegex().Matches(text).Count;
        if (PhoneRegex().IsMatch(text)) found["phone"]       = PhoneRegex().Matches(text).Count;
        if (SsnRegex()  .IsMatch(text)) found["ssn"]         = SsnRegex()  .Matches(text).Count;
        if (CardRegex() .IsMatch(text)) found["credit_card"] = CardRegex() .Matches(text).Count;

        return new()
        {
            ["has_pii"]     = found.Count > 0,
            ["pii_types"]   = found,
            ["text_length"] = text.Length,
        };
    }

    [Tool("Remove or mask PII from a response before delivering to user.")]
    public Dictionary<string, object> SanitizeResponse(string text, string piiTypes = "")
    {
        var sanitized = EmailRegex().Replace(text, "[EMAIL REDACTED]");
        sanitized     = PhoneRegex().Replace(sanitized, "[PHONE REDACTED]");
        sanitized     = SsnRegex()  .Replace(sanitized, "[SSN REDACTED]");
        sanitized     = CardRegex() .Replace(sanitized, "[CARD REDACTED]");

        return new()
        {
            ["sanitized_text"] = sanitized,
            ["was_modified"]   = sanitized != text,
        };
    }
}
