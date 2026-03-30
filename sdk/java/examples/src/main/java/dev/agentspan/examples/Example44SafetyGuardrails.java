// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.examples;

import dev.agentspan.Agent;
import dev.agentspan.Agentspan;
import dev.agentspan.annotations.Tool;
import dev.agentspan.enums.Strategy;
import dev.agentspan.internal.ToolRegistry;
import dev.agentspan.model.AgentResult;
import dev.agentspan.model.ToolDef;

import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Example 44 — Safety Guardrails Pipeline (PII detection and sanitization)
 *
 * <p>Demonstrates a sequential pipeline where a safety checker agent scans
 * the primary agent's output for PII and sanitizes it:
 *
 * <pre>
 * helpful_assistant → safety_checker
 * </pre>
 *
 * <p>This pattern uses tool-based PII detection rather than the built-in
 * guardrail system, showing how sequential agents can enforce safety policies
 * through explicit scanning and redaction.
 */
public class Example44SafetyGuardrails {

    static class SafetyTools {
        private static final Map<String, Pattern> PII_PATTERNS = Map.of(
            "email", Pattern.compile("[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}"),
            "phone", Pattern.compile("\\b\\d{3}[-.\\s]?\\d{3}[-.\\s]?\\d{4}\\b"),
            "ssn", Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b"),
            "credit_card", Pattern.compile("\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b")
        );

        @Tool(name = "check_pii", description = "Check text for personally identifiable information (PII)")
        public Map<String, Object> checkPii(String text) {
            Map<String, Integer> found = new java.util.LinkedHashMap<>();
            for (Map.Entry<String, Pattern> entry : PII_PATTERNS.entrySet()) {
                Matcher m = entry.getValue().matcher(text);
                int count = 0;
                while (m.find()) count++;
                if (count > 0) found.put(entry.getKey(), count);
            }
            return Map.of(
                "has_pii", !found.isEmpty(),
                "pii_types", found,
                "text_length", text.length()
            );
        }

        @Tool(name = "sanitize_response", description = "Remove or mask PII from a response before delivering to user")
        public Map<String, Object> sanitizeResponse(String text, String piiTypes) {
            String sanitized = text;
            sanitized = PII_PATTERNS.get("email").matcher(sanitized).replaceAll("[EMAIL REDACTED]");
            sanitized = PII_PATTERNS.get("phone").matcher(sanitized).replaceAll("[PHONE REDACTED]");
            sanitized = PII_PATTERNS.get("ssn").matcher(sanitized).replaceAll("[SSN REDACTED]");
            sanitized = PII_PATTERNS.get("credit_card").matcher(sanitized).replaceAll("[CARD REDACTED]");
            return Map.of(
                "sanitized_text", sanitized,
                "was_modified", !sanitized.equals(text)
            );
        }
    }

    public static void main(String[] args) {
        List<ToolDef> safetyTools = ToolRegistry.fromInstance(new SafetyTools());

        // Main assistant generates responses
        Agent assistant = Agent.builder()
            .name("helpful_assistant")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a helpful customer service assistant. Answer questions "
                + "about account details, contact information, and general inquiries. "
                + "When providing information, include relevant details.")
            .build();

        // Safety checker scans the response for PII
        Agent safetyChecker = Agent.builder()
            .name("safety_checker")
            .model(Settings.LLM_MODEL)
            .instructions(
                "You are a safety reviewer. Check the previous agent's response "
                + "for any PII (emails, phone numbers, SSNs, credit card numbers). "
                + "Use check_pii on the response text. If PII is found, use "
                + "sanitize_response to clean it. Output only the sanitized version.")
            .tools(safetyTools)
            .build();

        // Pipeline: generate → check and sanitize
        Agent pipeline = Agent.builder()
            .name("safety_pipeline")
            .model(Settings.LLM_MODEL)
            .instructions("Generate a response, then have the safety checker scan and sanitize it.")
            .agents(assistant, safetyChecker)
            .strategy(Strategy.SEQUENTIAL)
            .build();

        AgentResult result = Agentspan.run(pipeline,
            "What are the contact details for our support team? "
            + "Include email support@company.com and phone 555-123-4567.");
        result.printResult();

        Agentspan.shutdown();
    }
}
