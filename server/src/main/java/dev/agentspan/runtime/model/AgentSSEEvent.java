/*
 * Copyright (c) 2025 Agentspan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Event DTO for SSE streaming. Each event represents a semantic agent-level
 * state change (thinking, tool call, guardrail result, HITL pause, etc.).
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AgentSSEEvent {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private long id;
    private String type;
    private String workflowId;
    private String content;
    private String toolName;
    private Object args;
    private Object result;
    private String target;
    private Object output;
    private String guardrailName;
    private Map<String, Object> pendingTool;
    private long timestamp;
    // context_condensed fields
    private Integer messagesBefore;
    private Integer messagesAfter;
    private Integer exchangesCondensed;

    public AgentSSEEvent() {}

    private AgentSSEEvent(String type, String workflowId) {
        this.type = type;
        this.workflowId = workflowId;
        this.timestamp = System.currentTimeMillis();
    }

    // ── Factory methods ──────────────────────────────────────────────

    public static AgentSSEEvent thinking(String workflowId, String taskRef) {
        AgentSSEEvent e = new AgentSSEEvent("thinking", workflowId);
        e.content = taskRef;
        return e;
    }

    public static AgentSSEEvent toolCall(String workflowId, String toolName, Object args) {
        AgentSSEEvent e = new AgentSSEEvent("tool_call", workflowId);
        e.toolName = toolName;
        e.args = args;
        return e;
    }

    public static AgentSSEEvent toolResult(String workflowId, String toolName, Object result) {
        AgentSSEEvent e = new AgentSSEEvent("tool_result", workflowId);
        e.toolName = toolName;
        e.result = result;
        return e;
    }

    public static AgentSSEEvent handoff(String workflowId, String target) {
        AgentSSEEvent e = new AgentSSEEvent("handoff", workflowId);
        e.target = target;
        return e;
    }

    public static AgentSSEEvent waiting(String workflowId, Map<String, Object> pendingTool) {
        AgentSSEEvent e = new AgentSSEEvent("waiting", workflowId);
        e.pendingTool = pendingTool;
        return e;
    }

    public static AgentSSEEvent guardrailPass(String workflowId, String name) {
        AgentSSEEvent e = new AgentSSEEvent("guardrail_pass", workflowId);
        e.guardrailName = name;
        return e;
    }

    public static AgentSSEEvent guardrailFail(String workflowId, String name, String message) {
        AgentSSEEvent e = new AgentSSEEvent("guardrail_fail", workflowId);
        e.guardrailName = name;
        e.content = message;
        return e;
    }

    public static AgentSSEEvent error(String workflowId, String taskRef, String message) {
        AgentSSEEvent e = new AgentSSEEvent("error", workflowId);
        e.content = message;
        e.toolName = taskRef;
        return e;
    }

    public static AgentSSEEvent done(String workflowId, Object output) {
        AgentSSEEvent e = new AgentSSEEvent("done", workflowId);
        e.output = output;
        return e;
    }

    public static AgentSSEEvent contextCondensed(
            String workflowId, String trigger,
            int messagesBefore, int messagesAfter, int exchangesCondensed) {
        AgentSSEEvent e = new AgentSSEEvent("context_condensed", workflowId);
        e.content = trigger;
        e.messagesBefore = messagesBefore;
        e.messagesAfter = messagesAfter;
        e.exchangesCondensed = exchangesCondensed;
        return e;
    }

    public static AgentSSEEvent subagentStart(String workflowId, String subagentIdentifier, String prompt) {
        AgentSSEEvent e = new AgentSSEEvent("subagent_start", workflowId);
        e.target = subagentIdentifier;
        e.content = prompt != null ? prompt : "";
        return e;
    }

    public static AgentSSEEvent subagentStop(String workflowId, String subagentIdentifier, String result) {
        AgentSSEEvent e = new AgentSSEEvent("subagent_stop", workflowId);
        e.target = subagentIdentifier;
        e.result = result != null ? result : "";
        return e;
    }

    // ── Serialization ────────────────────────────────────────────────

    public String toJson() {
        try {
            return MAPPER.writeValueAsString(this);
        } catch (JsonProcessingException ex) {
            return "{\"type\":\"error\",\"content\":\"Serialization failed\"}";
        }
    }

    // ── Getters / Setters ────────────────────────────────────────────

    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getWorkflowId() { return workflowId; }
    public void setWorkflowId(String workflowId) { this.workflowId = workflowId; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getToolName() { return toolName; }
    public void setToolName(String toolName) { this.toolName = toolName; }
    public Object getArgs() { return args; }
    public void setArgs(Object args) { this.args = args; }
    public Object getResult() { return result; }
    public void setResult(Object result) { this.result = result; }
    public String getTarget() { return target; }
    public void setTarget(String target) { this.target = target; }
    public Object getOutput() { return output; }
    public void setOutput(Object output) { this.output = output; }
    public String getGuardrailName() { return guardrailName; }
    public void setGuardrailName(String guardrailName) { this.guardrailName = guardrailName; }
    public Map<String, Object> getPendingTool() { return pendingTool; }
    public void setPendingTool(Map<String, Object> pendingTool) { this.pendingTool = pendingTool; }
    public long getTimestamp() { return timestamp; }
    public void setTimestamp(long timestamp) { this.timestamp = timestamp; }
    public Integer getMessagesBefore() { return messagesBefore; }
    public void setMessagesBefore(Integer messagesBefore) { this.messagesBefore = messagesBefore; }
    public Integer getMessagesAfter() { return messagesAfter; }
    public void setMessagesAfter(Integer messagesAfter) { this.messagesAfter = messagesAfter; }
    public Integer getExchangesCondensed() { return exchangesCondensed; }
    public void setExchangesCondensed(Integer exchangesCondensed) { this.exchangesCondensed = exchangesCondensed; }
}
