// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.examples;

import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.annotations.Tool;
import org.conductoross.conductor.ai.enums.OnFail;
import org.conductoross.conductor.ai.enums.Position;
import org.conductoross.conductor.ai.internal.ToolRegistry;
import org.conductoross.conductor.ai.model.AgentResult;
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.ToolDef;

import java.util.List;
import java.util.Map;

/**
 * Example 21 — Regex Guardrails (server-side pattern matching)
 *
 * <p>Demonstrates {@code guardrailType="regex"} which compiles as a
 * Conductor InlineTask on the server — no worker process needed.
 *
 * <p>Two regex guardrails block PII from the agent's output:
 * <ul>
 *   <li>Block email addresses (on_fail=RETRY)</li>
 *   <li>Block SSNs (on_fail=RAISE)</li>
 * </ul>
 */
public class Example21RegexGuardrails {

    static class ProfileTools {
        @Tool(name = "get_user_profile", description = "Retrieve a user's profile from the database")
        public Map<String, Object> getUserProfile(String userId) {
            return Map.of(
                "name", "Alice Johnson",
                "email", "alice.johnson@example.com",
                "ssn", "123-45-6789",
                "department", "Engineering",
                "role", "Senior Developer"
            );
        }
    }

    public static void main(String[] args) {
        AgentRuntime runtime = new AgentRuntime();
        List<ToolDef> tools = ToolRegistry.fromInstance(new ProfileTools());

        // ── Block email addresses ─────────────────────────────────────────
        GuardrailDef noEmails = GuardrailDef.builder()
            .name("no_email_addresses")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .guardrailType("regex")
            .config(Map.of(
                "patterns", List.of("[\\w.+-]+@[\\w-]+\\.[\\w.-]+"),
                "mode", "block",
                "message", "Response must not contain email addresses. Redact them."
            ))
            .build();

        // ── Block SSNs ────────────────────────────────────────────────────
        GuardrailDef noSsn = GuardrailDef.builder()
            .name("no_ssn")
            .position(Position.OUTPUT)
            .onFail(OnFail.RAISE)
            .guardrailType("regex")
            .config(Map.of(
                "patterns", List.of("\\b\\d{3}-\\d{2}-\\d{4}\\b"),
                "mode", "block",
                "message", "Response must not contain Social Security Numbers."
            ))
            .build();

        Agent agent = Agent.builder()
            .name("hr_assistant")
            .model(Settings.LLM_MODEL)
            .tools(tools)
            .instructions(
                "You are an HR assistant. When asked about employees, look up their "
                + "profile and share ALL the details you find.")
            .guardrails(List.of(noEmails, noSsn))
            .build();

        AgentResult result = runtime.run(agent, "Tell me everything about user U-001.");
        result.printResult();

        runtime.shutdown();
    }
}
