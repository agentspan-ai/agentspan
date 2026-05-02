// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.enums;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * What to do when a guardrail fails.
 */
public enum OnFail {
    @JsonProperty("retry")
    RETRY,

    @JsonProperty("raise")
    RAISE,

    @JsonProperty("fix")
    FIX,

    @JsonProperty("human")
    HUMAN;

    public String toJsonValue() {
        try {
            return OnFail.class.getField(name())
                .getAnnotation(JsonProperty.class).value();
        } catch (NoSuchFieldException e) {
            return name().toLowerCase();
        }
    }
}
