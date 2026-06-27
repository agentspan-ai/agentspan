// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.guardrail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.conductoross.conductor.ai.enums.OnFail;
import org.conductoross.conductor.ai.enums.Position;
import org.conductoross.conductor.ai.model.GuardrailDef;
import org.conductoross.conductor.ai.model.GuardrailResult;
import org.junit.jupiter.api.Test;

/**
 * Pure unit tests for guardrail builder defaults and validation.
 *
 * <p>Fix 3: the default {@code onFail} must be {@link OnFail#RAISE} (was RETRY).
 * Fix 5: building a guardrail with {@code onFail=HUMAN} AND {@code position=INPUT}
 * must throw {@link IllegalArgumentException} (parity with Python's ValueError).
 */
class GuardrailDefaultsTest {

    // ── Fix 3: default onFail = RAISE ─────────────────────────────────────

    @Test
    void custom_guardrail_default_on_fail_is_raise() {
        GuardrailDef g = Guardrail.of("g", c -> GuardrailResult.pass()).build();
        assertEquals(OnFail.RAISE, g.getOnFail(), "Guardrail default onFail must be RAISE");
    }

    @Test
    void external_guardrail_default_on_fail_is_raise() {
        GuardrailDef g = Guardrail.external("g").build();
        assertEquals(OnFail.RAISE, g.getOnFail(), "external Guardrail default onFail must be RAISE");
    }

    @Test
    void regex_guardrail_default_on_fail_is_raise() {
        GuardrailDef g = RegexGuardrail.builder().name("r").patterns("x").build();
        assertEquals(OnFail.RAISE, g.getOnFail(), "RegexGuardrail default onFail must be RAISE");
    }

    @Test
    void llm_guardrail_default_on_fail_is_raise() {
        GuardrailDef g = LLMGuardrail.builder()
                .name("l")
                .model("openai/gpt-4o-mini")
                .policy("p")
                .build();
        assertEquals(OnFail.RAISE, g.getOnFail(), "LLMGuardrail default onFail must be RAISE");
    }

    // ── Fix 5: human + input is invalid ───────────────────────────────────

    @Test
    void human_input_guardrail_is_rejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Guardrail.of("g", c -> GuardrailResult.pass())
                        .position(Position.INPUT)
                        .onFail(OnFail.HUMAN)
                        .build(),
                "onFail=HUMAN with position=INPUT must be rejected");
    }

    @Test
    void human_output_guardrail_is_allowed() {
        GuardrailDef g = Guardrail.of("g", c -> GuardrailResult.pass())
                .position(Position.OUTPUT)
                .onFail(OnFail.HUMAN)
                .build();
        assertEquals(OnFail.HUMAN, g.getOnFail());
        assertEquals(Position.OUTPUT, g.getPosition());
    }
}
