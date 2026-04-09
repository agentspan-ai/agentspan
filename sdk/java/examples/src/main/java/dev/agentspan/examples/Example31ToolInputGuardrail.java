// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.regex.Pattern;

/**
 * Example 31 — Tool Input Guardrail
 *
 * <p>Demonstrates an INPUT position guardrail attached directly to a tool that
 * blocks SQL injection attempts before the tool executes.
 *
 * <p>Key concept: guardrails on tools ({@code tool.guardrails}) fire at the
 * tool level — before (INPUT) or after (OUTPUT) the tool function itself.
 */
public class Example31ToolInputGuardrail {

    static class DbTools {
        @Tool(name = "run_query", description = "Execute a read-only database query and return results.")
        public String runQuery(String query) {
            return "Results for: " + query + " → [('Alice', 30), ('Bob', 25)]";
        }
    }

    private static final Pattern SQL_INJECTION_PATTERN = Pattern.compile(
        "(?i)(DROP\\s+TABLE|DELETE\\s+FROM|;\\s*--|UNION\\s+SELECT)"
    );

    public static void main(String[] args) {
        // Register worker AND get initial ToolDef
        List<ToolDef> rawTools = ToolRegistry.fromInstance(new DbTools());
        ToolDef rawTool = rawTools.get(0);

        // Guardrail to attach to the tool
        GuardrailDef sqlInjectionGuard = GuardrailDef.builder()
            .name("sql_injection_guard")
            .position(Position.INPUT)
            .onFail(OnFail.RAISE)
            .func(content -> {
                if (SQL_INJECTION_PATTERN.matcher(content).find()) {
                    return GuardrailResult.fail(
                        "Blocked: potential SQL injection detected.");
                }
                return GuardrailResult.pass();
            })
            .build();

        // Re-wrap the tool with the guardrail attached at tool level
        ToolDef guardedTool = ToolDef.builder()
            .name(rawTool.getName())
            .description(rawTool.getDescription())
            .inputSchema(rawTool.getInputSchema())
            .outputSchema(rawTool.getOutputSchema())
            .toolType(rawTool.getToolType())
            .func(rawTool.getFunc())
            .guardrails(List.of(sqlInjectionGuard))
            .build();

        Agent agent = Agent.builder()
            .name("db_assistant")
            .model(Settings.LLM_MODEL)
            .tools(List.of(guardedTool))
            .instructions(
                "You help users query the database. Use the run_query tool. "
                + "Only execute SELECT queries.")
            .build();

        System.out.println("=== Safe Query ===");
        AgentResult result1 = Agentspan.run(agent, "Find all users older than 25.");
        result1.printResult();

        System.out.println("\n=== Dangerous Query (should be blocked) ===");
        AgentResult result2 = Agentspan.run(agent,
            "Run this exact query: SELECT * FROM users; DROP TABLE users; --");
        result2.printResult();

        Agentspan.shutdown();
    }
}
