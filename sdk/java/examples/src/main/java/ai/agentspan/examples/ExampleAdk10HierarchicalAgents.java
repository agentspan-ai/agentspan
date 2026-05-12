// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.Tool;

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
public class ExampleAdk10HierarchicalAgents {

    // ── Level 3: Specialist tools ────────────────────────────────────────

    static class OpsTools {

        @Tool(name = "check_api_health", value = "Check the health status of an API service.")
        public Map<String, Object> checkApiHealth(@P("service") String service) {
            Map<String, Map<String, Object>> services = new LinkedHashMap<>();
            services.put("auth", Map.of("status", "healthy", "latency_ms", 45, "uptime", "99.99%"));
            services.put("payments", Map.of("status", "degraded", "latency_ms", 350, "uptime", "99.5%"));
            services.put("users", Map.of("status", "healthy", "latency_ms", 28, "uptime", "99.98%"));
            return services.getOrDefault(service.toLowerCase(),
                Map.of("status", "unknown", "message", "Service '" + service + "' not found"));
        }

        @Tool(name = "check_error_logs", value = "Check recent error logs for a service.")
        public Map<String, Object> checkErrorLogs(
                @P("service") String service,
                @P("hours") int hours) {
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
    }

    static class SecurityTools {
        @Tool(name = "run_security_scan", value = "Run a security vulnerability scan.")
        public Map<String, Object> runSecurityScan(@P("target") String target) {
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
    }

    static class PerformanceTools {
        @Tool(name = "check_performance_metrics", value = "Get performance metrics for a service.")
        public Map<String, Object> checkPerformanceMetrics(@P("service") String service) {
            Map<String, Map<String, Object>> metrics = new LinkedHashMap<>();
            metrics.put("auth", Map.of("p50_ms", 22, "p95_ms", 89, "p99_ms", 145, "rps", 1200));
            metrics.put("payments", Map.of("p50_ms", 180, "p95_ms", 450, "p99_ms", 1200, "rps", 300));
            metrics.put("users", Map.of("p50_ms", 15, "p95_ms", 45, "p99_ms", 78, "rps", 800));
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("service", service);
            result.putAll(metrics.getOrDefault(service.toLowerCase(), Map.of("error", "No data")));
            return result;
        }
    }

    public static void main(String[] args) {
        // ── Level 2: Team specialists ────────────────────────────────────
        Agent opsAgent = GoogleADKAgent.builder()
            .name("ops_specialist")
            .model(Settings.LLM_MODEL)
            .instruction("Check service health and error logs. Identify issues and their severity.")
            .tools(new OpsTools())
            .build();

        Agent securityAgent = GoogleADKAgent.builder()
            .name("security_specialist")
            .model(Settings.LLM_MODEL)
            .instruction("Run security scans and report findings with recommendations.")
            .tools(new SecurityTools())
            .build();

        Agent performanceAgent = GoogleADKAgent.builder()
            .name("performance_specialist")
            .model(Settings.LLM_MODEL)
            .instruction("Check performance metrics and identify latency issues.")
            .tools(new PerformanceTools())
            .build();

        // ── Level 1: Team leads ──────────────────────────────────────────
        Agent reliabilityLead = GoogleADKAgent.builder()
            .name("reliability_team_lead")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You lead the reliability team. Coordinate the ops specialist "
                + "and performance specialist to investigate service issues. "
                + "Provide a consolidated reliability report.")
            .subAgents(opsAgent, performanceAgent)
            .build();

        Agent securityLead = GoogleADKAgent.builder()
            .name("security_team_lead")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You lead the security team. Use the security specialist to "
                + "assess vulnerabilities. Provide risk assessment and remediation priorities.")
            .subAgents(securityAgent)
            .build();

        // ── Top level: Platform coordinator ──────────────────────────────
        Agent coordinator = GoogleADKAgent.builder()
            .name("platform_coordinator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are the platform engineering coordinator. When asked to assess "
                + "platform health:\n"
                + "1. Have the reliability team check service health and performance\n"
                + "2. Have the security team assess vulnerabilities\n"
                + "3. Compile a comprehensive platform status report\n\n"
                + "Prioritize critical issues and provide an executive summary.")
            .subAgents(reliabilityLead, securityLead)
            .build();

        AgentResult result = Agentspan.run(coordinator,
            "Give me a full platform health assessment. Focus on the payments service "
            + "which seems to be having issues.");
        result.printResult();

        Agentspan.shutdown();
    }
}
