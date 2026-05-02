// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.guardrail;

import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;
import dev.agentspan.model.GuardrailDef;
import dev.agentspan.model.GuardrailResult;

import java.util.function.Function;

/**
 * A custom or external validation guardrail for agent input or output.
 *
 * <p>Use this when you need a guardrail beyond the built-in {@link LLMGuardrail} and
 * {@link RegexGuardrail}. Two modes:
 *
 * <ul>
 *   <li><b>Custom</b> — provide a local {@code Function<String, GuardrailResult>}.
 *       The function is registered as a Conductor worker under the given name.</li>
 *   <li><b>External</b> — reference an existing Conductor worker by name (no local function).</li>
 * </ul>
 *
 * <pre>{@code
 * // Custom local guardrail
 * GuardrailDef noBadWords = Guardrail.of("no_bad_words", content -> {
 *     boolean ok = !content.toLowerCase().contains("badword");
 *     return new GuardrailResult(ok, ok ? "" : "Response contained prohibited language.");
 * }).position(Position.OUTPUT).onFail(OnFail.RETRY).build();
 *
 * // External guardrail — references a running Conductor worker
 * GuardrailDef safety = Guardrail.external("corporate_safety_check")
 *     .position(Position.OUTPUT)
 *     .onFail(OnFail.RAISE)
 *     .build();
 * }</pre>
 */
public class Guardrail {

    private Guardrail() {}

    /** Start building a custom guardrail backed by a local function. */
    public static Builder of(String name, Function<String, GuardrailResult> func) {
        return new Builder(name, func, false);
    }

    /** Start building an external guardrail that references a named Conductor worker. */
    public static Builder external(String name) {
        return new Builder(name, null, true);
    }

    public static class Builder {
        private final String name;
        private final Function<String, GuardrailResult> func;
        private final boolean isExternal;
        private Position position = Position.OUTPUT;
        private OnFail onFail = OnFail.RETRY;
        private int maxRetries = 3;

        private Builder(String name, Function<String, GuardrailResult> func, boolean isExternal) {
            if (name == null || name.isEmpty()) throw new IllegalArgumentException("Guardrail name is required");
            this.name = name;
            this.func = func;
            this.isExternal = isExternal;
        }

        public Builder position(Position position) { this.position = position; return this; }
        public Builder onFail(OnFail onFail) { this.onFail = onFail; return this; }
        public Builder maxRetries(int maxRetries) { this.maxRetries = maxRetries; return this; }

        public GuardrailDef build() {
            String guardrailType = isExternal ? "external" : "custom";
            return GuardrailDef.builder()
                    .name(name)
                    .position(position)
                    .onFail(onFail)
                    .maxRetries(maxRetries)
                    .guardrailType(guardrailType)
                    .func(func)
                    .build();
        }
    }
}
