// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.model;

import dev.agentspan.enums.EventType;

import java.util.Map;

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
    private final String workflowId;
    private final String guardrailName;
    private final String target;

    public AgentEvent(
            EventType type,
            String content,
            String toolName,
            Map<String, Object> args,
            Object result,
            Object output,
            String workflowId,
            String guardrailName,
            String target) {
        this.type = type;
        this.content = content;
        this.toolName = toolName;
        this.args = args;
        this.result = result;
        this.output = output;
        this.workflowId = workflowId;
        this.guardrailName = guardrailName;
        this.target = target;
    }

    public EventType getType() { return type; }
    public String getContent() { return content; }
    public String getToolName() { return toolName; }
    public Map<String, Object> getArgs() { return args; }
    public Object getResult() { return result; }
    public Object getOutput() { return output; }
    public String getWorkflowId() { return workflowId; }
    public String getGuardrailName() { return guardrailName; }
    public String getTarget() { return target; }

    /**
     * Create an AgentEvent from a raw map (as parsed from SSE JSON).
     */
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

        return new AgentEvent(
            type,
            (String) data.get("content"),
            (String) data.get("toolName"),
            (Map<String, Object>) data.get("args"),
            data.get("result"),
            data.get("output"),
            (String) data.getOrDefault("workflowId", ""),
            (String) data.get("guardrailName"),
            (String) data.get("target")
        );
    }

    @Override
    public String toString() {
        return "AgentEvent{type=" + type + ", content=" + content + "}";
    }
}
