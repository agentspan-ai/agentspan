// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.enums;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Types of events emitted during agent execution.
 */
public enum EventType {
    @JsonProperty("thinking")
    THINKING,

    @JsonProperty("tool_call")
    TOOL_CALL,

    @JsonProperty("tool_result")
    TOOL_RESULT,

    @JsonProperty("handoff")
    HANDOFF,

    @JsonProperty("waiting")
    WAITING,

    @JsonProperty("message")
    MESSAGE,

    @JsonProperty("error")
    ERROR,

    @JsonProperty("done")
    DONE,

    @JsonProperty("guardrail_pass")
    GUARDRAIL_PASS,

    @JsonProperty("guardrail_fail")
    GUARDRAIL_FAIL;

    public String toJsonValue() {
        try {
            return EventType.class.getField(name())
                .getAnnotation(JsonProperty.class).value();
        } catch (NoSuchFieldException e) {
            return name().toLowerCase();
        }
    }
}
