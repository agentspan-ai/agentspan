// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.Collections;
import java.util.Map;

/**
 * A single tool call awaiting human approval inside a {@link AgentEvent}
 * of type {@code waiting}.
 *
 * <p>One HUMAN task gates a whole batch of tool calls with a single
 * {@code {approved, reason}} verdict — the array on the event is the
 * load-bearing field. Iterate it to see every tool the LLM proposed in
 * this turn.
 */
public final class PendingToolCall {

    private final String name;
    private final Map<String, Object> args;

    public PendingToolCall(String name, Map<String, Object> args) {
        this.name = name;
        this.args = args != null ? args : Collections.emptyMap();
    }

    /** The tool's registered name (e.g. {@code "publish_article"}). */
    public String getName() {
        return name;
    }

    /** The LLM-generated arguments for this tool call. */
    public Map<String, Object> getArgs() {
        return args;
    }

    @Override
    public String toString() {
        return "PendingToolCall{name=" + name + ", args=" + args + "}";
    }
}
