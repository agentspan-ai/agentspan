// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.GuardrailDef;
import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.GuardrailResult;

import java.util.List;

/**
 * Example 10 — Guardrails
 *
 * <p>Demonstrates input and output guardrails using the {@link GuardrailDef} annotation.
 * Guardrails can validate, reject, or fix agent inputs and outputs.
 */
public class Example10Guardrails {

    static class ContentGuardrails {

        /** Check that input doesn't contain profanity. */
        @GuardrailDef(
            name = "no_profanity_input",
            position = Position.INPUT,
            onFail = OnFail.RAISE
        )
        public GuardrailResult noProfanityInput(String input) {
            String[] blocked = {"spam", "hate", "violent"};
            String lowerInput = input.toLowerCase();
            for (String word : blocked) {
                if (lowerInput.contains(word)) {
                    return GuardrailResult.fail("Input contains inappropriate content: " + word);
                }
            }
            return GuardrailResult.pass();
        }

        /** Check that output doesn't contain personal information. */
        @GuardrailDef(
            name = "no_pii_output",
            position = Position.OUTPUT,
            onFail = OnFail.FIX,
            maxRetries = 2
        )
        public GuardrailResult noPiiOutput(String output) {
            // Simple PII check: look for SSN-like patterns
            if (output.matches(".*\\d{3}-\\d{2}-\\d{4}.*")) {
                // Fix by removing the SSN pattern
                String fixed = output.replaceAll("\\d{3}-\\d{2}-\\d{4}", "[REDACTED]");
                return GuardrailResult.fix(fixed);
            }
            // Check for credit card-like patterns
            if (output.matches(".*\\d{4}[- ]\\d{4}[- ]\\d{4}[- ]\\d{4}.*")) {
                String fixed = output.replaceAll("\\d{4}[- ]\\d{4}[- ]\\d{4}[- ]\\d{4}", "[CARD REDACTED]");
                return GuardrailResult.fix(fixed);
            }
            return GuardrailResult.pass();
        }

        /** Check that output is not too long. */
        @GuardrailDef(
            name = "length_check",
            position = Position.OUTPUT,
            onFail = OnFail.RETRY,
            maxRetries = 3
        )
        public GuardrailResult lengthCheck(String output) {
            if (output != null && output.length() > 2000) {
                return GuardrailResult.fail(
                    "Response is too long (" + output.length() + " chars). Please be more concise.");
            }
            return GuardrailResult.pass();
        }
    }

    public static void main(String[] args) {
        ContentGuardrails guardrailFns = new ContentGuardrails();
        List<dev.agentspan.model.GuardrailDef> guardrails =
            ToolRegistry.guardrailsFromInstance(guardrailFns);

        Agent agent = Agent.builder()
            .name("safe_assistant")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a helpful assistant. Provide clear and concise answers. "
                + "Never include personal information like SSNs or credit card numbers.")
            .guardrails(guardrails)
            .build();

        System.out.println("=== Normal Query ===");
        AgentResult result1 = Agentspan.run(agent, "What are the best practices for Java development?");
        result1.printResult();

        System.out.println("\n=== Query That May Trigger Output Guardrail ===");
        AgentResult result2 = Agentspan.run(agent,
            "Give me an example of what a fake SSN format looks like in documentation");
        result2.printResult();

        Agentspan.shutdown();
    }
}
