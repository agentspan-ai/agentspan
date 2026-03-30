// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailDef;

import java.util.List;
import java.util.Map;

/**
 * Example 21 — Regex Guardrails (server-side pattern matching)
 *
 * <p>Demonstrates {@code guardrailType="regex"} which compiles as a
 * Conductor InlineTask on the server — no Python/Java worker process needed.
 *
 * <p>Two regex guardrails are applied:
 * <ul>
 *   <li>Block PII patterns (SSN, credit card numbers)</li>
 *   <li>Block profanity patterns</li>
 * </ul>
 */
public class Example21RegexGuardrails {

    public static void main(String[] args) {
        // ── Regex guardrail: block SSN patterns ────────────────────────────

        GuardrailDef noPii = GuardrailDef.builder()
            .name("no_pii")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(3)
            .guardrailType("regex")
            .config(Map.of(
                "patterns", List.of(
                    "\\b\\d{3}-\\d{2}-\\d{4}\\b",             // SSN
                    "\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b"  // Credit card
                ),
                "mode", "block",
                "message",
                    "Response contains PII (SSN or credit card number). "
                    + "Remove all sensitive personal information."
            ))
            .build();

        // ── Regex guardrail: require structured format ──────────────────────

        GuardrailDef requireJson = GuardrailDef.builder()
            .name("require_json_structure")
            .position(Position.OUTPUT)
            .onFail(OnFail.RETRY)
            .maxRetries(3)
            .guardrailType("regex")
            .config(Map.of(
                "patterns", List.of("^(?!.*\\{)"),   // Must contain at least one {
                "mode", "allow",                      // allow = must match to pass
                "message",
                    "Response must include JSON-formatted data. "
                    + "Please format your response with JSON."
            ))
            .build();

        // ── Agent with regex guardrails ────────────────────────────────────

        Agent agent = Agent.builder()
            .name("safe_data_agent")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a data assistant. Always respond with JSON-formatted data. "
                + "Never include SSNs, credit card numbers, or other PII in your responses.")
            .guardrails(List.of(noPii))
            .build();

        AgentResult result = Agentspan.run(agent,
            "Provide a sample customer record in JSON format.");
        result.printResult();

        Agentspan.shutdown();
    }
}
