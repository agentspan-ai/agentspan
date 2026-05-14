// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk26 — Safety Guardrails.
//
// Sequential pipeline (assistant -> safety_checker) that scans the
// response for PII and sanitizes it before delivery.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var assistant = GoogleADKAgent.Builder()
    .Name("helpful_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a helpful customer service assistant. Answer questions " +
        "about account details, contact information, and general inquiries. " +
        "When providing information, include relevant details.")
    .Build();

var safetyChecker = GoogleADKAgent.Builder()
    .Name("safety_checker")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a safety reviewer. Check the previous agent's response " +
        "for any PII (emails, phone numbers, SSNs, credit card numbers). " +
        "Use check_pii on the response text. If PII is found, use " +
        "sanitize_response to clean it. Pass the clean version along.")
    .Tools(new SafetyTools())
    .Build();

var safePipeline = GoogleADKAgent.Builder()
    .Name("safe_assistant")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate a safe assistant pipeline. Run sub-agents sequentially: " +
        "1) helpful_assistant answers the user, 2) safety_checker reviews the " +
        "response, scans for PII, and sanitizes if needed.")
    .SubAgents(assistant, safetyChecker)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(safePipeline,
    "What are the contact details for our support team? " +
    "Include email support@company.com and phone 555-123-4567.");
result.PrintResult();

internal sealed class SafetyTools
{
    private static readonly Dictionary<string, System.Text.RegularExpressions.Regex> _patterns = new()
    {
        ["email"]       = new(@"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        ["phone"]       = new(@"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
        ["ssn"]         = new(@"\b\d{3}-\d{2}-\d{4}\b"),
        ["credit_card"] = new(@"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    };

    [Tool(Name = "check_pii", Description = "Check text for personally identifiable information (PII).")]
    public Dictionary<string, object> CheckPii(string text)
    {
        var found = new Dictionary<string, int>();
        foreach (var (k, rx) in _patterns)
        {
            var count = rx.Matches(text).Count;
            if (count > 0) found[k] = count;
        }
        return new Dictionary<string, object>
        {
            ["has_pii"]     = found.Count > 0,
            ["pii_types"]   = found,
            ["text_length"] = text.Length,
        };
    }

    [Tool(Name = "sanitize_response",
        Description = "Remove or mask PII from a response before delivering to user.")]
    public Dictionary<string, object> SanitizeResponse(string text, string pii_types)
    {
        var sanitized = text;
        sanitized = _patterns["email"].Replace(sanitized, "[EMAIL REDACTED]");
        sanitized = _patterns["phone"].Replace(sanitized, "[PHONE REDACTED]");
        sanitized = _patterns["ssn"].Replace(sanitized, "[SSN REDACTED]");
        sanitized = _patterns["credit_card"].Replace(sanitized, "[CARD REDACTED]");
        return new Dictionary<string, object>
        {
            ["sanitized_text"] = sanitized,
            ["was_modified"]   = sanitized != text,
        };
    }
}
