// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.Annotations.Schema;
import com.google.adk.tools.FunctionTool;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Example Adk 10 — Hierarchical Agents
 *
 * <p>Java port of <code>sdk/python/examples/adk/10_hierarchical_agents.py</code>.
 *
 * <p>Demonstrates: multi-level agent delegation. A top-level coordinator
 * delegates to team leads, which delegate to specialist agents with tools.
 */
public class Example10HierarchicalAgents {

    // ── Level 3: Specialist tools ────────────────────────────────────────

    @Schema(description = "Check the health status of an API service.")
    public static Map<String, Object> checkApiHealth(
            @Schema(name = "service", description = "Service name") String service) {
        Map<String, Map<String, Object>> services = new LinkedHashMap<>();
        services.put("auth", Map.of("status", "healthy", "latency_ms", 45, "uptime", "99.99%"));
        services.put("payments", Map.of("status", "degraded", "latency_ms", 350, "uptime", "99.5%"));
        services.put("users", Map.of("status", "healthy", "latency_ms", 28, "uptime", "99.98%"));
        return services.getOrDefault(service.toLowerCase(),
            Map.of("status", "unknown", "message", "Service '" + service + "' not found"));
    }

    @Schema(description = "Check recent error logs for a service.")
    public static Map<String, Object> checkErrorLogs(
            @Schema(name = "service", description = "Service name") String service,
            @Schema(name = "hours", description = "Lookback hours") int hours) {
        Map<String, Map<String, Object>> logs = new LinkedHashMap<>();
        logs.put("auth", Map.of("errors", 2, "warnings", 5, "top_error", "Token validation timeout"));
        logs.put("payments", Map.of("errors", 47, "warnings", 120, "top_error", "Gateway timeout on /charge"));
        logs.put("users", Map.of("errors", 0, "warnings", 1, "top_error", "None"));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("service", service);
        result.put("period_hours", hours);
        result.putAll(logs.getOrDefault(service.toLowerCase(), Map.of("errors", -1)));
        return result;
    }

    @Schema(description = "Run a security vulnerability scan.")
    public static Map<String, Object> runSecurityScan(
            @Schema(name = "target", description = "Scan target") String target) {
        return Map.of(
            "target", target,
            "vulnerabilities", Map.of(
                "critical", 0,
                "high", 1,
                "medium", 3,
                "low", 7
            ),
            "top_finding", "Outdated TLS 1.1 still enabled on /legacy endpoint",
            "recommendation", "Disable TLS 1.1, enforce TLS 1.3"
        );
    }

    @Schema(description = "Get performance metrics for a service.")
    public static Map<String, Object> checkPerformanceMetrics(
            @Schema(name = "service", description = "Service name") String service) {
        Map<String, Map<String, Object>> metrics = new LinkedHashMap<>();
        metrics.put("auth", Map.of("p50_ms", 22, "p95_ms", 89, "p99_ms", 145, "rps", 1200));
        metrics.put("payments", Map.of("p50_ms", 180, "p95_ms", 450, "p99_ms", 1200, "rps", 300));
        metrics.put("users", Map.of("p50_ms", 15, "p95_ms", 45, "p99_ms", 78, "rps", 800));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("service", service);
        result.putAll(metrics.getOrDefault(service.toLowerCase(), Map.of("error", "No data")));
        return result;
    }

    public static void main(String[] args) {
        // ── Level 2: Team specialists ────────────────────────────────────
        LlmAgent opsAgent = LlmAgent.builder()
            .name("ops_specialist")
            .description("Checks API health and error logs to identify service issues.")
            .model(Settings.LLM_MODEL)
            .instruction("Check service health and error logs. Identify issues and their severity.")
            .tools(
                FunctionTool.create(Example10HierarchicalAgents.class, "checkApiHealth"),
                FunctionTool.create(Example10HierarchicalAgents.class, "checkErrorLogs"))
            .build();

        LlmAgent securityAgent = LlmAgent.builder()
            .name("security_specialist")
            .description("Runs security vulnerability scans and reports remediation recommendations.")
            .model(Settings.LLM_MODEL)
            .instruction("Run security scans and report findings with recommendations.")
            .tools(FunctionTool.create(Example10HierarchicalAgents.class, "runSecurityScan"))
            .build();

        LlmAgent performanceAgent = LlmAgent.builder()
            .name("performance_specialist")
            .description("Checks performance metrics and identifies latency issues for services.")
            .model(Settings.LLM_MODEL)
            .instruction("Check performance metrics and identify latency issues.")
            .tools(FunctionTool.create(Example10HierarchicalAgents.class, "checkPerformanceMetrics"))
            .build();

        // ── Level 1: Team leads ──────────────────────────────────────────
        LlmAgent reliabilityLead = LlmAgent.builder()
            .name("reliability_team_lead")
            .description("Leads ops and performance specialists to produce a consolidated reliability report.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You lead the reliability team. Coordinate the ops specialist "
                + "and performance specialist to investigate service issues. "
                + "Provide a consolidated reliability report.")
            .subAgents(opsAgent, performanceAgent)
            .build();

        LlmAgent securityLead = LlmAgent.builder()
            .name("security_team_lead")
            .description("Leads security specialists to produce risk assessments and remediation plans.")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You lead the security team. Use the security specialist to "
                + "assess vulnerabilities. Provide risk assessment and remediation priorities.")
            .subAgents(securityAgent)
            .build();

        // ── Top level: Platform coordinator ──────────────────────────────
        LlmAgent coordinator = LlmAgent.builder()
            .name("platform_coordinator")
            .description("Top-level platform engineering coordinator that orchestrates reliability and security teams.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are the platform engineering coordinator. When asked to assess
                platform health:
                1. Have the reliability team check service health and performance
                2. Have the security team assess vulnerabilities
                3. Compile a comprehensive platform status report

                Prioritize critical issues and provide an executive summary.
                """)
            .subAgents(reliabilityLead, securityLead)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Give me a full platform health assessment. Focus on the payments service "
            + "which seems to be having issues.");
        result.printResult();

        Agentspan.shutdown();
    }
}
