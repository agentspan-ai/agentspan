// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

import dev.agentspan.enums.OnFail;
import dev.agentspan.enums.Position;

import java.util.Map;
import java.util.function.Function;

/**
 * Runtime model for a guardrail definition.
 *
 * <p>This is the runtime counterpart to the {@link dev.agentspan.annotations.GuardrailDef}
 * annotation. Use {@link Builder} to create instances.
 */
public class GuardrailDef {
    private final String name;
    private final Position position;
    private final OnFail onFail;
    private final int maxRetries;
    private final Function<String, GuardrailResult> func;
    private final String guardrailType;
    private final Map<String, Object> config;

    private GuardrailDef(Builder builder) {
        this.name = builder.name;
        this.position = builder.position;
        this.onFail = builder.onFail;
        this.maxRetries = builder.maxRetries;
        this.func = builder.func;
        this.guardrailType = builder.guardrailType;
        this.config = builder.config;
    }

    public String getName() { return name; }
    public Position getPosition() { return position; }
    public OnFail getOnFail() { return onFail; }
    public int getMaxRetries() { return maxRetries; }
    public Function<String, GuardrailResult> getFunc() { return func; }
    public String getGuardrailType() { return guardrailType; }
    public Map<String, Object> getConfig() { return config; }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private String name;
        private Position position = Position.OUTPUT;
        private OnFail onFail = OnFail.RAISE;
        private int maxRetries = 3;
        private Function<String, GuardrailResult> func;
        private String guardrailType = "custom";
        private Map<String, Object> config;

        public Builder name(String name) { this.name = name; return this; }
        public Builder position(Position position) { this.position = position; return this; }
        public Builder onFail(OnFail onFail) { this.onFail = onFail; return this; }
        public Builder maxRetries(int maxRetries) { this.maxRetries = maxRetries; return this; }
        public Builder func(Function<String, GuardrailResult> func) { this.func = func; return this; }
        public Builder guardrailType(String guardrailType) { this.guardrailType = guardrailType; return this; }
        public Builder config(Map<String, Object> config) { this.config = config; return this; }

        public GuardrailDef build() {
            if (name == null || name.isEmpty()) {
                throw new IllegalArgumentException("GuardrailDef requires a name");
            }
            return new GuardrailDef(this);
        }
    }
}
