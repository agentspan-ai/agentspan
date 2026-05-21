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
public class Example26SafetyGuardrails {

    private static final Map<String, Pattern> PATTERNS = new LinkedHashMap<>();
    static {
        PATTERNS.put("email", Pattern.compile("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b"));
        PATTERNS.put("phone", Pattern.compile("\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b"));
        PATTERNS.put("ssn", Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b"));
        PATTERNS.put("credit_card", Pattern.compile("\\b\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}[-\\s]?\\d{4}\\b"));
    }

    @Schema(description = "Check text for personally identifiable information (PII).")
    public static Map<String, Object> checkPii(
            @Schema(name = "text", description = "Text to scan for PII") String text) {
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

    @Schema(description = "Remove or mask PII from a response before delivering to user.")
    public static Map<String, Object> sanitizeResponse(
            @Schema(name = "text", description = "Text to sanitize") String text,
            @Schema(name = "pii_types", description = "Comma-separated PII categories to redact") String piiTypes) {
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

    public static void main(String[] args) {
        LlmAgent assistant = LlmAgent.builder()
            .name("helpful_assistant")
            .description("Answers customer service questions with relevant details.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a helpful customer service assistant. Answer questions
                about account details, contact information, and general inquiries.
                When providing information, include relevant details.
                """)
            .build();

        LlmAgent safetyChecker = LlmAgent.builder()
            .name("safety_checker")
            .description("Scans the assistant's reply for PII and sanitizes it before delivery.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a safety reviewer. Check the previous safePipeline's response
                for any PII (emails, phone numbers, SSNs, credit card numbers).
                Use check_pii on the response text. If PII is found, use
                sanitize_response to clean it. Pass the clean version along.
                """)
            .tools(
                FunctionTool.create(Example26SafetyGuardrails.class, "checkPii"),
                FunctionTool.create(Example26SafetyGuardrails.class, "sanitizeResponse"))
            .build();

        LlmAgent safePipeline = LlmAgent.builder()
            .name("safe_assistant")
            .description("Sequential pipeline: assistant answers, then safety_checker redacts PII.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You orchestrate a safe assistant pipeline. Run sub-agents sequentially:
                1) helpful_assistant answers the user, 2) safety_checker reviews the
                response, scans for PII, and sanitizes if needed.
                """)
            .subAgents(assistant, safetyChecker)
            .build();

        AgentResult result = Agentspan.run(safePipeline,
            "What are the contact details for our support team? "
            + "Include email support@company.com and phone 555-123-4567.");
        result.printResult();

        Agentspan.shutdown();
    }
}
