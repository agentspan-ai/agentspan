// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.enums;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Where a guardrail is applied in the agent pipeline.
 */
public enum Position {
    @JsonProperty("input")
    INPUT,

    @JsonProperty("output")
    OUTPUT;

    public String toJsonValue() {
        try {
            return Position.class.getField(name())
                .getAnnotation(JsonProperty.class).value();
        } catch (NoSuchFieldException e) {
            return name().toLowerCase();
        }
    }
}
