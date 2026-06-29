// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.conductoross.conductor.ai.enums.EventType;

/**
 * A single event from a streaming agent execution.
 */
public class AgentEvent {
    private final EventType type;
    private final String content;
    private final String toolName;
    private final Map<String, Object> args;
    private final Object result;
    private final Object output;
    private final String executionId;
    private final String guardrailName;
    private final String target;
    private final Map<String, Object> pendingTool;

    public AgentEvent(
            EventType type,
            String content,
            String toolName,
            Map<String, Object> args,
            Object result,
            Object output,
            String executionId,
            String guardrailName,
            String target) {
        this(type, content, toolName, args, result, output, executionId, guardrailName, target, null);
    }

    public AgentEvent(
            EventType type,
            String content,
            String toolName,
            Map<String, Object> args,
            Object result,
            Object output,
            String executionId,
            String guardrailName,
            String target,
            Map<String, Object> pendingTool) {
        this.type = type;
        this.content = content;
        this.toolName = toolName;
        this.args = args;
        this.result = result;
        this.output = output;
        this.executionId = executionId;
        this.guardrailName = guardrailName;
        this.target = target;
        this.pendingTool = pendingTool;
    }

    public EventType getType() {
        return type;
    }

    public String getContent() {
        return content;
    }

    public String getToolName() {
        return toolName;
    }

    public Map<String, Object> getArgs() {
        return args;
    }

    public Object getResult() {
        return result;
    }

    public Object getOutput() {
        return output;
    }

    public String getExecutionId() {
        return executionId;
    }

    public String getGuardrailName() {
        return guardrailName;
    }

    public String getTarget() {
        return target;
    }

    /**
     * Raw {@code pendingTool} block from a {@code waiting} SSE event, or
     * {@code null} for any other event type. Contains at minimum
     * {@code taskRefName}; for approval-gated batches it also contains
     * {@code toolCalls} — the array of tools the LLM proposed this turn.
     *
     * <p>Most consumers want {@link #getPendingToolCalls()} instead.
     */
    public Map<String, Object> getPendingTool() {
        return pendingTool;
    }

    /**
     * Typed view of {@code pendingTool.toolCalls}. Returns an empty list
     * (never {@code null}) when no calls are pending — including for non-
     * {@code waiting} events.
     *
     * <p>One HUMAN task gates the whole batch with one {@code {approved,
     * reason}} verdict. Iterate to see every tool covered by the gate.
     */
    @SuppressWarnings("unchecked")
    public List<PendingToolCall> getPendingToolCalls() {
        if (pendingTool == null) return Collections.emptyList();
        Object raw = pendingTool.get("toolCalls");
        if (!(raw instanceof List<?>)) return Collections.emptyList();
        List<?> list = (List<?>) raw;
        List<PendingToolCall> calls = new ArrayList<>(list.size());
        for (Object entry : list) {
            if (!(entry instanceof Map<?, ?>)) continue;
            Map<String, Object> map = (Map<String, Object>) entry;
            Object name = map.get("name");
            Object args = map.get("args");
            calls.add(new PendingToolCall(
                    name != null ? name.toString() : null,
                    args instanceof Map<?, ?> ? (Map<String, Object>) args : null));
        }
        return calls;
    }

    /**
     * Create an AgentEvent from a raw map (as parsed from SSE JSON).
     */
    /** Internal keys injected by the server that should not be shown as tool arguments. */
    private static final Set<String> INTERNAL_KEYS =
            new HashSet<>(Arrays.asList("__agentspan_ctx__", "_agent_state", "method"));

    @SuppressWarnings("unchecked")
    public static AgentEvent fromMap(Map<String, Object> data) {
        String typeStr = (String) data.get("type");
        EventType type = null;
        if (typeStr != null) {
            for (EventType et : EventType.values()) {
                if (et.toJsonValue().equals(typeStr)) {
                    type = et;
                    break;
                }
            }
            if (type == null) {
                try {
                    type = EventType.valueOf(typeStr.toUpperCase());
                } catch (IllegalArgumentException e) {
                    type = EventType.MESSAGE;
                }
            }
        }

        // Strip internal server keys from tool call args
        Map<String, Object> rawArgs = (Map<String, Object>) data.get("args");
        Map<String, Object> cleanArgs = null;
        if (rawArgs != null) {
            cleanArgs = new LinkedHashMap<>();
            for (Map.Entry<String, Object> entry : rawArgs.entrySet()) {
                if (!INTERNAL_KEYS.contains(entry.getKey())) {
                    cleanArgs.put(entry.getKey(), entry.getValue());
                }
            }
        }

        Object rawPendingTool = data.get("pendingTool");
        Map<String, Object> pendingTool =
                rawPendingTool instanceof Map<?, ?> ? (Map<String, Object>) rawPendingTool : null;

        return new AgentEvent(
                type,
                (String) data.get("content"),
                (String) data.get("toolName"),
                cleanArgs,
                data.get("result"),
                data.get("output"),
                (String) data.getOrDefault("executionId", ""),
                (String) data.get("guardrailName"),
                (String) data.get("target"),
                pendingTool);
    }

    @Override
    public String toString() {
        return "AgentEvent{type=" + type + ", content=" + content + "}";
    }
}
