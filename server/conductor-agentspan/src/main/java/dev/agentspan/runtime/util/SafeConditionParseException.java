/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */
package dev.agentspan.runtime.util;

/**
 * Thrown by {@link SafeConditionInterpreter#parse(String)} on a syntactically
 * invalid or whitelist-disallowed expression. Plan validation surfaces this
 * as the {@code error} on the PAC result so the offending plan is rejected
 * before any task is emitted.
 */
public class SafeConditionParseException extends RuntimeException {

    public SafeConditionParseException(String message) {
        super(message);
    }
}
