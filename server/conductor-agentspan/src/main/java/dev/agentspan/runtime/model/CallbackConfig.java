/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Callback configuration for agent lifecycle hooks.
 *
 * <p>Each callback maps to a Conductor worker task that is inserted at the
 * specified position in the compiled workflow. The worker task is registered
 * by the SDK (same pattern as {@code @tool} functions).</p>
 *
 * <p>Supported positions:</p>
 * <ul>
 *   <li>{@code before_agent} — before the main DoWhile loop</li>
 *   <li>{@code after_agent} — after the main DoWhile loop</li>
 *   <li>{@code before_model} — before LLM_CHAT_COMPLETE (inside loop)</li>
 *   <li>{@code after_model} — after LLM_CHAT_COMPLETE (inside loop)</li>
 *   <li>{@code before_tool} — before FORK_JOIN_DYNAMIC (tool_call branch)</li>
 *   <li>{@code after_tool} — after JOIN (tool_call branch)</li>
 * </ul>
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class CallbackConfig {

    /**
     * Callback position: before_agent, after_agent, before_model, after_model,
     * before_tool, after_tool.
     */
    private String position;

    /** Conductor worker task name (registered by the SDK). */
    private String taskName;
}
