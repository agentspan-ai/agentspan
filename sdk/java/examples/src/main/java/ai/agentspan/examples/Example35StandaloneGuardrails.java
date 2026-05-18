// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples;

import ai.agentspan.model.GuardrailResult;

import java.util.function.Function;
import java.util.regex.Pattern;

/**
 * Example 35 — Standalone Guardrails
 *
 * <p>Demonstrates using guardrail logic as plain Java functions — no agent,
 * no server connection needed. The guardrail functions run entirely in-process,
 * making this useful for:
 * <ul>
 *   <li>Unit testing your guardrail logic in isolation</li>
 *   <li>Pre-validating content before submitting it to an agent</li>
 *   <li>Reusing the same validation functions in multiple agents</li>
 * </ul>
 *
 * <p>This example runs entirely without a server — no {@code Agentspan.run()} call.
 */
public class Example35StandaloneGuardrails {

    static class GuardrailFunctions {

        private static final Pattern CREDIT_CARD_PATTERN =
            Pattern.compile("\\b\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}[\\s-]?\\d{4}\\b");

        private static final Pattern SSN_PATTERN =
            Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b");

        /** Rejects content containing credit card numbers or SSNs. */
        public static GuardrailResult noPii(String content) {
            if (CREDIT_CARD_PATTERN.matcher(content).find()) {
                return GuardrailResult.fail("Credit card number detected in content.");
            }
            if (SSN_PATTERN.matcher(content).find()) {
                return GuardrailResult.fail("Social Security Number detected in content.");
            }
            return GuardrailResult.pass();
        }

        /** Rejects content containing common profanity. */
        public static GuardrailResult noProfanity(String content) {
            String[] blocked = {"damn", "hell", "crap"};
            String lower = content.toLowerCase();
            for (String word : blocked) {
                if (lower.contains(word)) {
                    return GuardrailResult.fail("Profanity detected: \"" + word + "\"");
                }
            }
            return GuardrailResult.pass();
        }

        /** Rejects content that exceeds 100 words. */
        public static GuardrailResult wordLimit(String content) {
            if (content == null || content.isBlank()) {
                return GuardrailResult.pass();
            }
            long wordCount = java.util.Arrays.stream(content.trim().split("\\s+"))
                .filter(w -> !w.isEmpty())
                .count();
            if (wordCount > 100) {
                return GuardrailResult.fail(
                    "Content too long: " + wordCount + " words (limit: 100).");
            }
            return GuardrailResult.pass();
        }
    }

    /**
     * Runs all supplied guardrail checks against {@code text} and prints a
     * PASS / FAIL summary for each.
     */
    @SafeVarargs
    private static void validate(
            String text,
            String label,
            Function<String, GuardrailResult>... checks) {

        System.out.println("\n--- " + label + " ---");
        System.out.println("Input: \"" + (text.length() > 80 ? text.substring(0, 77) + "..." : text) + "\"");

        String[] names = {"noPii", "noProfanity", "wordLimit"};
        for (int i = 0; i < checks.length; i++) {
            GuardrailResult result = checks[i].apply(text);
            String checkName = i < names.length ? names[i] : "check" + i;
            if (result.isPassed()) {
                System.out.println("  [PASS] " + checkName);
            } else {
                System.out.println("  [FAIL] " + checkName + " — " + result.getMessage());
            }
        }
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) {

        System.out.println("=== Standalone Guardrail Validation (no server required) ===");

        // Test 1: Clean text — all checks should pass
        validate(
            "Hello, your order #1234 has shipped and will arrive Friday.",
            "Test 1: Clean text",
            GuardrailFunctions::noPii,
            GuardrailFunctions::noProfanity,
            GuardrailFunctions::wordLimit
        );

        // Test 2: Credit card number — noPii should fail
        validate(
            "Your card on file is 4532-0150-1234-5678. Order confirmed.",
            "Test 2: Credit card number",
            GuardrailFunctions::noPii,
            GuardrailFunctions::noProfanity,
            GuardrailFunctions::wordLimit
        );

        // Test 3: Profanity — noProfanity should fail
        validate(
            "What the hell happened to my order?",
            "Test 3: Profanity",
            GuardrailFunctions::noPii,
            GuardrailFunctions::noProfanity,
            GuardrailFunctions::wordLimit
        );

        // Test 4: Over word limit — wordLimit should fail
        String longText = "word ".repeat(150).trim();
        validate(
            longText,
            "Test 4: 150-word text (limit is 100)",
            GuardrailFunctions::noPii,
            GuardrailFunctions::noProfanity,
            GuardrailFunctions::wordLimit
        );

        System.out.println("\nAll tests complete. No server connection was needed.");
    }
}
