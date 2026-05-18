// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Data Security Pipeline — controlled data flow with redaction.
//
// A sequential pipeline enforces a security boundary:
//   collector >> validator >> responder
//
// - collector: Fetches raw user data (includes PII).
// - validator: Redacts sensitive fields (SSN, balance, email).
// - responder: Presents the safe, redacted data to the user.
//
// Requirements:
//   - Agentspan server with LLM support
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using System.Text.Json;
using Agentspan;
using Agentspan.Examples;

// ── Data collector ────────────────────────────────────────────

var collector = new Agent("data_collector_43")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a data collection agent. When asked about a user, " +
        "call fetch_user_data with their ID. Pass the raw data along " +
        "to the next agent for security review.",
    Tools = ToolRegistry.FromInstance(new DataTools()),
};

// ── Security validator ────────────────────────────────────────

var validator = new Agent("security_validator_43")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a security validator. Review data for sensitive information " +
        "(SSN, account balances, email addresses). Use the redact_sensitive_fields " +
        "tool to redact any sensitive data before passing it along. " +
        "Only pass redacted data to the next agent.",
    Tools = ToolRegistry.FromInstance(new RedactionTools()),
};

// ── Responder ─────────────────────────────────────────────────

var responder = new Agent("responder_43")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a customer service agent. The previous agent has already " +
        "validated and redacted sensitive fields. Present ALL fields from the " +
        "validated data: share non-redacted values normally, and for any field " +
        "marked ***REDACTED***, state that it is restricted for security reasons. " +
        "Do not refuse to answer — the data has already been made safe.",
};

// ── Pipeline ──────────────────────────────────────────────────

var pipeline = collector >> validator >> responder;

// ── Run ───────────────────────────────────────────────────────

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(
    pipeline,
    "Tell me everything about user U001 including their financial details.");

result.PrintResult();

// ── Tool classes ──────────────────────────────────────────────

internal sealed class DataTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> Users = new()
    {
        ["U001"] = new()
        {
            ["name"]            = "Alice Johnson",
            ["email"]           = "alice@example.com",
            ["role"]            = "admin",
            ["ssn_last4"]       = "1234",
            ["account_balance"] = 15000.00,
        },
        ["U002"] = new()
        {
            ["name"]            = "Bob Smith",
            ["email"]           = "bob@example.com",
            ["role"]            = "user",
            ["ssn_last4"]       = "5678",
            ["account_balance"] = 3200.00,
        },
    };

    [Tool("Fetch user data from the database.")]
    public Dictionary<string, object> FetchUserData(string userId)
        => Users.TryGetValue(userId, out var user)
            ? user
            : new() { ["error"] = $"User {userId} not found" };
}

internal sealed class RedactionTools
{
    private static readonly HashSet<string> SensitiveKeys =
        ["ssn_last4", "account_balance", "email"];

    [Tool("Redact sensitive fields from data before responding to users.")]
    public Dictionary<string, object> RedactSensitiveFields(string data)
    {
        Dictionary<string, object>? parsed;
        try { parsed = JsonSerializer.Deserialize<Dictionary<string, object>>(data); }
        catch { return new() { ["error"] = "Could not parse data for redaction" }; }

        if (parsed is null) return new() { ["error"] = "Null data" };

        var redacted = new Dictionary<string, object>();
        foreach (var (k, v) in parsed)
            redacted[k] = SensitiveKeys.Contains(k) ? "***REDACTED***" : v;

        return new() { ["redacted_data"] = redacted };
    }
}
