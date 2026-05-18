// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk25 — CaMeL Security.
//
// A CaMeL-inspired sequential pipeline (collector -> validator -> responder)
// enforcing controlled data flow and redacting sensitive fields before
// responding to users.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.Text.Json;
using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

var collector = GoogleADKAgent.Builder()
    .Name("data_collector")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a data collection agent. When asked about a user, " +
        "call fetch_user_data with their ID. Pass the raw data along " +
        "to the next agent for security review.")
    .Tools(new CollectorTools())
    .Build();

var validator = GoogleADKAgent.Builder()
    .Name("security_validator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a security validator. Review data for sensitive information " +
        "(SSN, account balances, email addresses). Use the redact_sensitive_fields " +
        "tool to redact any sensitive data before passing it along. " +
        "Only pass redacted data to the next agent.")
    .Tools(new ValidatorTools())
    .Build();

var responder = GoogleADKAgent.Builder()
    .Name("responder")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are a customer service agent. Use the validated, redacted data " +
        "to answer the user's question. NEVER reveal redacted information. " +
        "If data shows ***REDACTED***, explain that the information is " +
        "restricted for security reasons.")
    .Build();

var pipeline = GoogleADKAgent.Builder()
    .Name("secure_data_pipeline")
    .Model(Settings.LlmModel)
    .Instruction(
        "You orchestrate a secure data pipeline. Run sub-agents sequentially: " +
        "1) data_collector fetches raw user data, 2) security_validator redacts " +
        "sensitive fields, 3) responder formats the final answer using only " +
        "the redacted data.")
    .SubAgents(collector, validator, responder)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(pipeline,
    "Tell me everything about user U001 including their financial details.");
result.PrintResult();

internal sealed class CollectorTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _users = new()
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

    [Tool(Name = "fetch_user_data", Description = "Fetch user data from the database.")]
    public Dictionary<string, object> FetchUserData(string user_id)
        => _users.TryGetValue(user_id, out var v)
            ? v
            : new Dictionary<string, object> { ["error"] = $"User {user_id} not found" };
}

internal sealed class ValidatorTools
{
    private static readonly HashSet<string> _sensitive = new() { "ssn_last4", "account_balance", "email" };

    [Tool(Name = "redact_sensitive_fields",
        Description = "Redact sensitive fields from data before responding to users.")]
    public Dictionary<string, object> RedactSensitiveFields(string data)
    {
        Dictionary<string, object>? parsed;
        try
        {
            parsed = JsonSerializer.Deserialize<Dictionary<string, object>>(data);
        }
        catch
        {
            return new Dictionary<string, object> { ["error"] = "Could not parse data for redaction" };
        }
        if (parsed is null)
            return new Dictionary<string, object> { ["error"] = "Could not parse data for redaction" };

        var redacted = new Dictionary<string, object>();
        foreach (var (k, v) in parsed)
            redacted[k] = _sensitive.Contains(k) ? "***REDACTED***" : v;
        return new Dictionary<string, object> { ["redacted_data"] = redacted };
    }
}
