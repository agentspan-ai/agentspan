// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

/**
 * Result returned from a guardrail function.
 */
public class GuardrailResult {
    private final boolean passed;
    private final String message;
    private final String fixedOutput;

    private GuardrailResult(boolean passed, String message, String fixedOutput) {
        this.passed = passed;
        this.message = message;
        this.fixedOutput = fixedOutput;
    }

    /** Create a passing guardrail result. */
    public static GuardrailResult pass() {
        return new GuardrailResult(true, null, null);
    }

    /** Create a failing guardrail result with a message. */
    public static GuardrailResult fail(String message) {
        return new GuardrailResult(false, message, null);
    }

    /** Create a result with fixed/replacement output. */
    public static GuardrailResult fix(String fixedOutput) {
        return new GuardrailResult(false, null, fixedOutput);
    }

    public boolean isPassed() {
        return passed;
    }

    public String getMessage() {
        return message;
    }

    public String getFixedOutput() {
        return fixedOutput;
    }

    @Override
    public String toString() {
        return "GuardrailResult{passed=" + passed + ", message=" + message + "}";
    }
}
