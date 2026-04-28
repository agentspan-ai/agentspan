// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan;

import java.util.Map;

/**
 * Base class for composable agent lifecycle callbacks.
 *
 * <p>Subclass and override the hook methods you care about. Multiple handlers
 * can be registered on the same agent via {@link Agent.Builder#callbacks}; they
 * run in list order. Returning a non-empty map from any hook short-circuits
 * remaining handlers and uses the returned map as an override.
 *
 * <p>Registered positions and their task name patterns:
 * <ul>
 *   <li>{@code before_agent} → {@code {agentName}_before_agent}</li>
 *   <li>{@code after_agent}  → {@code {agentName}_after_agent}</li>
 *   <li>{@code before_model} → {@code {agentName}_before_model}</li>
 *   <li>{@code after_model}  → {@code {agentName}_after_model}</li>
 *   <li>{@code before_tool}  → {@code {agentName}_before_tool}</li>
 *   <li>{@code after_tool}   → {@code {agentName}_after_tool}</li>
 * </ul>
 *
 * <pre>{@code
 * class TimingHandler extends CallbackHandler {
 *     long t0;
 *     public Map<String, Object> onAgentStart(Map<String, Object> kwargs) {
 *         t0 = System.currentTimeMillis();
 *         return null;
 *     }
 *     public Map<String, Object> onAgentEnd(Map<String, Object> kwargs) {
 *         System.out.println("Took " + (System.currentTimeMillis() - t0) + "ms");
 *         return null;
 *     }
 * }
 * }</pre>
 */
public abstract class CallbackHandler {

    /** Called before the agent begins processing. Return non-null non-empty map to override. */
    public Map<String, Object> onAgentStart(Map<String, Object> kwargs) { return null; }

    /** Called after the agent finishes processing. Return non-null non-empty map to override. */
    public Map<String, Object> onAgentEnd(Map<String, Object> kwargs) { return null; }

    /** Called before each LLM call. Return non-null non-empty map to short-circuit the LLM. */
    public Map<String, Object> onModelStart(Map<String, Object> kwargs) { return null; }

    /** Called after each LLM call. Return non-null non-empty map to replace the response. */
    public Map<String, Object> onModelEnd(Map<String, Object> kwargs) { return null; }

    /** Called before each tool execution. Return non-null non-empty map to override. */
    public Map<String, Object> onToolStart(Map<String, Object> kwargs) { return null; }

    /** Called after each tool execution. Return non-null non-empty map to override. */
    public Map<String, Object> onToolEnd(Map<String, Object> kwargs) { return null; }
}
