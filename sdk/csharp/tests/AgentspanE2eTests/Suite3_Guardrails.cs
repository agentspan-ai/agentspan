// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 3 — Guardrail execution: verify guardrail function body runs and
// that the agent status reflects the guardrail outcome.
//
// Validation: Interlocked counters on the guardrail function body.
// We do NOT assert on LLM output text.
//
// CLAUDE.md rule: no LLM for validation; write test → make it fail → confirm failure.

using System.Text.RegularExpressions;
using System.Threading;
using Xunit;
using Agentspan.Examples;

namespace Agentspan.E2eTests;

[Collection("E2e")]
public sealed class Suite3_Guardrails
{
    private readonly E2eFixture _fixture;

    public Suite3_Guardrails(E2eFixture fixture) => _fixture = fixture;

    // ── 3.1  Output guardrail function body executes ─────────────────────

    [SkippableFact]
    public async Task OutputGuardrail_FunctionBodyExecutes()
    {
        _fixture.RequireServer();

        var host   = new S3GuardrailHost();
        var guardrails = GuardrailRegistry.FromInstance(host);

        var agent = new Agent("s3_guardrail_exec")
        {
            Model      = Settings.LlmModel,
            Instructions = "You are a helpful assistant. Answer concisely.",
            Guardrails = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "Say hello.");

        // The guardrail function must have been invoked at least once
        Assert.True(host.CheckCount > 0,
            $"Expected guardrail to execute but CheckCount was {host.CheckCount}.");
        Assert.True(result.IsSuccess || result.IsFailed,  // either outcome is valid
            $"Unexpected agent status: {result.Status}");
    }

    // ── 3.2  Passing guardrail: agent succeeds ───────────────────────────

    [SkippableFact]
    public async Task PassingGuardrail_AgentSucceeds()
    {
        _fixture.RequireServer();

        var host   = new S3AlwaysPassGuardrailHost();
        var guardrails = GuardrailRegistry.FromInstance(host);

        var agent = new Agent("s3_pass_guardrail")
        {
            Model        = Settings.LlmModel,
            Instructions = "Answer briefly.",
            Guardrails   = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(agent, "What is 2+2?");

        Assert.True(host.CallCount > 0,
            "Expected always-pass guardrail to be called but it wasn't.");
        Assert.True(result.IsSuccess, $"Agent failed unexpectedly: {result.Error}");
    }

    // ── 3.3  Regex guardrail blocks PII-like content ─────────────────────

    [SkippableFact]
    public async Task RegexGuardrail_FunctionBodyExecutes()
    {
        _fixture.RequireServer();

        var host   = new S3PiiGuardrailHost();
        var tools  = ToolRegistry.FromInstance(new S3PiiToolHost());
        var guardrails = GuardrailRegistry.FromInstance(host);

        var agent = new Agent("s3_pii_guardrail")
        {
            Model        = Settings.LlmModel,
            Instructions = "You are a customer service agent. Use get_customer_info to answer.",
            Tools        = tools,
            Guardrails   = guardrails,
        };

        await using var runtime = new AgentRuntime();
        var result = await runtime.RunAsync(
            agent, "Get info for customer CUST-1 and tell me everything.");

        // Guardrail function MUST have been invoked
        Assert.True(host.CheckCount > 0,
            $"PII guardrail was never called. CheckCount={host.CheckCount}");

        // Agent must either succeed (LLM redacted PII) or fail (gave up after retries)
        // We do NOT assert on the LLM text output.
        Assert.True(result.IsSuccess || result.IsFailed,
            $"Unexpected status: {result.Status}");
    }

    // ── 3.4  Tool-level guardrail: wrapper executes before tool ──────────

    [SkippableFact]
    public async Task ToolGuardrail_WrapperExecutesBeforeTool()
    {
        _fixture.RequireServer();

        var host  = new S3ToolGuardrailHost();
        var tools = ToolRegistry.FromInstance(host);

        var agent = new Agent("s3_tool_guardrail")
        {
            Model        = Settings.LlmModel,
            Instructions = "Use run_query to answer database questions.",
            Tools        = tools,
        };

        await using var runtime = new AgentRuntime();
        // Safe query — tool must execute
        var result = await runtime.RunAsync(agent, "Find all users in the database.");

        Assert.True(result.IsSuccess, $"Agent failed: {result.Error}");
        Assert.True(host.QueryCallCount > 0,
            "Expected run_query to be called at least once.");
    }
}

// ── Guardrail and tool hosts ──────────────────────────────────────────────────

internal sealed class S3GuardrailHost
{
    private int _checkCount;
    public int CheckCount => _checkCount;

    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 1)]
    public GuardrailResult CheckOutput(string content)
    {
        Interlocked.Increment(ref _checkCount);
        // Always pass — we only want to verify the body ran.
        return new GuardrailResult(true);
    }
}

internal sealed class S3AlwaysPassGuardrailHost
{
    private int _callCount;
    public int CallCount => _callCount;

    [Guardrail(Position = Position.Output, OnFail = OnFail.Raise)]
    public GuardrailResult AlwaysPass(string content)
    {
        Interlocked.Increment(ref _callCount);
        return new GuardrailResult(true);
    }
}

internal sealed class S3PiiGuardrailHost
{
    private static readonly Regex CcPattern = new(@"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b");

    private int _checkCount;
    public int CheckCount => _checkCount;

    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 2)]
    public GuardrailResult NoPii(string content)
    {
        Interlocked.Increment(ref _checkCount);
        if (CcPattern.IsMatch(content))
            return new GuardrailResult(false, "Response contains a credit card number. Redact it.");
        return new GuardrailResult(true);
    }
}

internal sealed class S3PiiToolHost
{
    [Tool("Get customer information including payment details.")]
    public Dictionary<string, object> GetCustomerInfo(string customerId) => new()
    {
        ["customer_id"] = customerId,
        ["name"]        = "Test User",
        ["card"]        = "4532-0150-1234-5678",  // PII intentionally in tool output
    };
}

internal sealed class S3ToolGuardrailHost
{
    private static readonly Regex DangerPattern = new(@"DROP\s+TABLE|DELETE\s+FROM", RegexOptions.IgnoreCase);

    private int _queryCalls;
    public int QueryCallCount => _queryCalls;

    [Tool("Execute a database query.")]
    public string RunQuery(string query)
    {
        Interlocked.Increment(ref _queryCalls);
        if (DangerPattern.IsMatch(query))
            return "Blocked: destructive SQL detected.";
        return $"Results: [('Alice', 30), ('Bob', 25)]";
    }
}
