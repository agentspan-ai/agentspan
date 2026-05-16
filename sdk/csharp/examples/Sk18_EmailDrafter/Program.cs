// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Sk18 — Email drafter with mock contact directory + send.
//
// Plugin functions: lookup_contact, today_date, send_email. The agent
// drafts the email body itself but uses tools for everything stateful.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using System.ComponentModel;
using System.Globalization;
using Agentspan;
using Agentspan.Examples;
using Agentspan.SemanticKernel;
using Microsoft.SemanticKernel;

namespace Agentspan.Examples.Sk18;

public sealed class EmailPlugin
{
    private static readonly Dictionary<string, string> Directory = new(StringComparer.OrdinalIgnoreCase)
    {
        ["alice"] = "alice@example.com",
        ["bob"]   = "bob@example.com",
        ["carol"] = "carol@example.com",
    };

    [KernelFunction, Description("Look up an email by first name. Returns 'NOT_FOUND' if missing.")]
    public string LookupContact([Description("first name")] string name)
        => Directory.TryGetValue(name, out var addr) ? addr : "NOT_FOUND";

    [KernelFunction, Description("Today's date in ISO format (yyyy-MM-dd) in UTC.")]
    public string TodayDate() => DateTime.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    [KernelFunction, Description("Pretend to send an email; returns a fake message id.")]
    public string SendEmail(
        [Description("recipient email")] string to,
        [Description("subject")]         string subject,
        [Description("body text")]       string body)
        => $"queued to={to} subject='{subject}' bytes={body.Length} id=MSG-{Guid.NewGuid().ToString()[..6]}";
}

public static class Program
{
    public static async Task Main()
    {
        var agent = SemanticKernelAgent.From(
            name:         "sk_emailer",
            model:        Settings.LlmModel,
            instructions: "Compose and send the requested email. Always include today's date in the body.",
            new EmailPlugin());

        await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
        var result = await runtime.RunAsync(
            agent,
            "Send Alice a 1-paragraph thank-you note for last week's design review.");
        result.PrintResult();
    }
}
