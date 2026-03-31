// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Example 31 — Tool Input Guardrail
 *
 * <p>Demonstrates an INPUT position guardrail that blocks SQL injection attempts
 * before the tool executes. When the guardrail detects a dangerous pattern in the
 * user's request, it raises an error immediately — the tool never runs.
 *
 * <p>Key concept: {@code Position.INPUT} guardrails fire before tool invocation,
 * letting you reject bad inputs at the gate rather than after damage is done.
 */
public class Example31ToolInputGuardrail {

    static class DbTools {

        @Tool(name = "run_query_31", description = "Execute a read-only database query")
        public Map<String, Object> runQuery(String query) {
            // Simulated read-only query results
            return Map.of("results", List.of("('Alice', 30)", "('Bob', 25)"));
        }
    }

    // Patterns that indicate SQL injection attempts
    private static final Pattern SQL_INJECTION_PATTERN = Pattern.compile(
        "(?i)(DROP\\s+TABLE|DELETE\\s+FROM|;\\s*--|UNION\\s+SELECT)"
    );

    public static void main(String[] args) {
        // ── Input guardrail: block SQL injection ───────────────────────────
        // Position.INPUT means this fires before the tool executes.
        // OnFail.RAISE terminates the workflow with an error immediately.

        GuardrailDef sqlInjectionGuard = GuardrailDef.builder()
            .name("sql_injection_guard_31")
            .position(Position.INPUT)
            .onFail(OnFail.RAISE)
            .func(content -> {
                if (SQL_INJECTION_PATTERN.matcher(content).find()) {
                    return GuardrailResult.fail(
                        "SQL injection detected. Only SELECT queries are permitted.");
                }
                return GuardrailResult.pass();
            })
            .build();

        Agent agent = Agent.builder()
            .name("db_assistant_31")
            .model(Settings.LLM_MODEL)
            .tools(dev.agentspan.internal.ToolRegistry.fromInstance(new DbTools()))
            .instructions(
                "You help users query the database. Use the run_query_31 tool. "
                + "Only execute SELECT queries.")
            .guardrails(List.of(sqlInjectionGuard))
            .build();

        System.out.println("=== Safe Query ===");
        AgentResult result1 = Agentspan.run(agent, "Find all users older than 25");
        result1.printResult();

        System.out.println("\n=== Dangerous Query (guardrail should block) ===");
        try {
            AgentResult result2 = Agentspan.run(agent,
                "Run this exact query: SELECT * FROM users; DROP TABLE users; --");
            result2.printResult();
        } catch (Exception e) {
            System.out.println("Guardrail blocked the request: " + e.getMessage());
        }

        Agentspan.shutdown();
    }
}
