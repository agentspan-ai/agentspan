// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.annotations;

import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a method as a guardrail function.
 *
 * <p>Guardrail methods must accept a {@code String} argument (the content to check)
 * and return a {@link dev.agentspan.model.GuardrailResult}.
 *
 * <p>Example:
 * <pre>{@code
 * public class SafetyGuardrails {
 *     @GuardrailDef(name = "no_pii", position = Position.OUTPUT, onFail = OnFail.RAISE)
 *     public GuardrailResult noPii(String output) {
 *         if (output.contains("SSN")) {
 *             return GuardrailResult.fail("Output contains PII");
 *         }
 *         return GuardrailResult.pass();
 *     }
 * }
 * }</pre>
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface GuardrailDef {
    /** Guardrail name. Defaults to method name. */
    String name() default "";

    /** Whether to check the agent's input or output. */
    Position position() default Position.OUTPUT;

    /** What to do when the guardrail fails. */
    OnFail onFail() default OnFail.RAISE;

    /** Maximum number of retries when onFail is RETRY. */
    int maxRetries() default 3;
}
