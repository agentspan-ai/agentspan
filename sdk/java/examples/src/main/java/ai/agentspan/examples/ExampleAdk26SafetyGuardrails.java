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
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Example Adk 26 — Safety Guardrails
 *
 * <p>Java port of <code>sdk/python/examples/adk/26_safety_guardrails.py</code>.
 *
 * <p>Demonstrates: sequential pipeline (assistant → safety_checker) that
 * scans the response for PII and sanitizes it before delivery.
 */
public class ExampleAdk26SafetyGuardrails {

    static class SafetyTools {

        private static final Map<String, Pattern> PATTERNS = new LinkedHashMap<>();
        static {
            PATTERNS.put("email", Pattern.compile("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b"));
            PATTERNS.put("phone", Pattern.compile("\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b"));
            PATTERNS.put("ssn", Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b"));
            PATTERNS.put("credit_card", Pattern.compile("\\b\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}\\b"));
        }

        @Tool(name = "check_pii", value = "Check text for personally identifiable information (PII).")
        public Map<String, Object> checkPii(@P("text") String text) {
            Map<String, Integer> found = new LinkedHashMap<>();
            for (Map.Entry<String, Pattern> entry : PATTERNS.entrySet()) {
                Matcher m = entry.getValue().matcher(text);
                int count = 0;
                while (m.find()) count++;
                if (count > 0) {
                    found.put(entry.getKey(), count);
                }
            }
            return Map.of(
                "has_pii", !found.isEmpty(),
                "pii_types", found,
                "text_length", text.length()
            );
        }

        @Tool(name = "sanitize_response", value = "Remove or mask PII from a response before delivering to user.")
        public Map<String, Object> sanitizeResponse(
                @P("text") String text,
                @P("pii_types") String piiTypes) {
            String sanitized = text;
            sanitized = PATTERNS.get("email").matcher(sanitized).replaceAll("[EMAIL REDACTED]");
            sanitized = PATTERNS.get("phone").matcher(sanitized).replaceAll("[PHONE REDACTED]");
            sanitized = PATTERNS.get("ssn").matcher(sanitized).replaceAll("[SSN REDACTED]");
            sanitized = PATTERNS.get("credit_card").matcher(sanitized).replaceAll("[CARD REDACTED]");
            return Map.of(
                "sanitized_text", sanitized,
                "was_modified", !sanitized.equals(text)
            );
        }
    }

    public static void main(String[] args) {
        Agent assistant = GoogleADKAgent.builder()
            .name("helpful_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a helpful customer service assistant. Answer questions "
                + "about account details, contact information, and general inquiries. "
                + "When providing information, include relevant details.")
            .build();

        Agent safetyChecker = GoogleADKAgent.builder()
            .name("safety_checker")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a safety reviewer. Check the previous agent's response "
                + "for any PII (emails, phone numbers, SSNs, credit card numbers). "
                + "Use check_pii on the response text. If PII is found, use "
                + "sanitize_response to clean it. Pass the clean version along.")
            .tools(new SafetyTools())
            .build();

        Agent safePipeline = GoogleADKAgent.builder()
            .name("safe_assistant")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You orchestrate a safe assistant pipeline. Run sub-agents sequentially: "
                + "1) helpful_assistant answers the user, 2) safety_checker reviews the "
                + "response, scans for PII, and sanitizes if needed.")
            .subAgents(assistant, safetyChecker)
            .build();

        AgentResult result = Agentspan.run(safePipeline,
            "What are the contact details for our support team? "
            + "Include email support@company.com and phone 555-123-4567.");
        result.printResult();

        Agentspan.shutdown();
    }
}
