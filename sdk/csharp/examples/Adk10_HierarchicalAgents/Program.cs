// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Adk10 — Hierarchical Agents.
//
// Multi-level agent delegation. A top-level coordinator delegates to
// team leads, which delegate to specialist agents with tools.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api
//   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini

using Agentspan;
using Agentspan.Examples;
using Agentspan.GoogleADK;

// ── Level 3: Specialists ─────────────────────────────────────
var opsAgent = GoogleADKAgent.Builder()
    .Name("ops_specialist")
    .Model(Settings.LlmModel)
    .Instruction("Check service health and error logs. Identify issues and their severity.")
    .Tools(new OpsTools())
    .Build();

var securityAgent = GoogleADKAgent.Builder()
    .Name("security_specialist")
    .Model(Settings.LlmModel)
    .Instruction("Run security scans and report findings with recommendations.")
    .Tools(new SecurityTools())
    .Build();

var performanceAgent = GoogleADKAgent.Builder()
    .Name("performance_specialist")
    .Model(Settings.LlmModel)
    .Instruction("Check performance metrics and identify latency issues.")
    .Tools(new PerformanceTools())
    .Build();

// ── Level 2: Team leads ──────────────────────────────────────
var reliabilityLead = GoogleADKAgent.Builder()
    .Name("reliability_team_lead")
    .Model(Settings.LlmModel)
    .Instruction(
        "You lead the reliability team. Coordinate the ops specialist " +
        "and performance specialist to investigate service issues. " +
        "Provide a consolidated reliability report.")
    .SubAgents(opsAgent, performanceAgent)
    .Build();

var securityLead = GoogleADKAgent.Builder()
    .Name("security_team_lead")
    .Model(Settings.LlmModel)
    .Instruction(
        "You lead the security team. Use the security specialist to " +
        "assess vulnerabilities. Provide risk assessment and remediation priorities.")
    .SubAgents(securityAgent)
    .Build();

// ── Top level ────────────────────────────────────────────────
var coordinator = GoogleADKAgent.Builder()
    .Name("platform_coordinator")
    .Model(Settings.LlmModel)
    .Instruction(
        "You are the platform engineering coordinator. When asked to assess platform health:\n" +
        "1. Have the reliability team check service health and performance\n" +
        "2. Have the security team assess vulnerabilities\n" +
        "3. Compile a comprehensive platform status report\n\n" +
        "Prioritize critical issues and provide an executive summary.")
    .SubAgents(reliabilityLead, securityLead)
    .Build();

await using var runtime = new AgentRuntime(new AgentRuntimeOptions { ServerUrl = Settings.ServerUrl });
var result = await runtime.RunAsync(coordinator,
    "Give me a full platform health assessment. Focus on the payments service " +
    "which seems to be having issues.");
result.PrintResult();

internal sealed class OpsTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _services = new(StringComparer.OrdinalIgnoreCase)
    {
        ["auth"]     = new() { ["status"] = "healthy",  ["latency_ms"] = 45,  ["uptime"] = "99.99%" },
        ["payments"] = new() { ["status"] = "degraded", ["latency_ms"] = 350, ["uptime"] = "99.5%"  },
        ["users"]    = new() { ["status"] = "healthy",  ["latency_ms"] = 28,  ["uptime"] = "99.98%" },
    };
    private static readonly Dictionary<string, Dictionary<string, object>> _logs = new(StringComparer.OrdinalIgnoreCase)
    {
        ["auth"]     = new() { ["errors"] = 2,  ["warnings"] = 5,   ["top_error"] = "Token validation timeout"  },
        ["payments"] = new() { ["errors"] = 47, ["warnings"] = 120, ["top_error"] = "Gateway timeout on /charge" },
        ["users"]    = new() { ["errors"] = 0,  ["warnings"] = 1,   ["top_error"] = "None"                       },
    };

    [Tool(Name = "check_api_health", Description = "Check the health status of an API service.")]
    public Dictionary<string, object> CheckApiHealth(string service)
        => _services.TryGetValue(service, out var v)
            ? v
            : new Dictionary<string, object> { ["status"] = "unknown", ["message"] = $"Service '{service}' not found" };

    [Tool(Name = "check_error_logs", Description = "Check recent error logs for a service.")]
    public Dictionary<string, object> CheckErrorLogs(string service, int hours)
    {
        var result = new Dictionary<string, object> { ["service"] = service, ["period_hours"] = hours };
        var data = _logs.TryGetValue(service, out var v) ? v : new Dictionary<string, object> { ["errors"] = -1 };
        foreach (var (k, val) in data) result[k] = val;
        return result;
    }
}

internal sealed class SecurityTools
{
    [Tool(Name = "run_security_scan", Description = "Run a security vulnerability scan.")]
    public Dictionary<string, object> RunSecurityScan(string target)
    {
        return new Dictionary<string, object>
        {
            ["target"]          = target,
            ["vulnerabilities"] = new Dictionary<string, object>
            {
                ["critical"] = 0, ["high"] = 1, ["medium"] = 3, ["low"] = 7,
            },
            ["top_finding"]    = "Outdated TLS 1.1 still enabled on /legacy endpoint",
            ["recommendation"] = "Disable TLS 1.1, enforce TLS 1.3",
        };
    }
}

internal sealed class PerformanceTools
{
    private static readonly Dictionary<string, Dictionary<string, object>> _metrics = new(StringComparer.OrdinalIgnoreCase)
    {
        ["auth"]     = new() { ["p50_ms"] = 22,  ["p95_ms"] = 89,  ["p99_ms"] = 145,  ["rps"] = 1200 },
        ["payments"] = new() { ["p50_ms"] = 180, ["p95_ms"] = 450, ["p99_ms"] = 1200, ["rps"] = 300  },
        ["users"]    = new() { ["p50_ms"] = 15,  ["p95_ms"] = 45,  ["p99_ms"] = 78,   ["rps"] = 800  },
    };

    [Tool(Name = "check_performance_metrics", Description = "Get performance metrics for a service.")]
    public Dictionary<string, object> CheckPerformanceMetrics(string service)
    {
        var result = new Dictionary<string, object> { ["service"] = service };
        var data = _metrics.TryGetValue(service, out var v) ? v : new Dictionary<string, object> { ["error"] = "No data" };
        foreach (var (k, val) in data) result[k] = val;
        return result;
    }
}
