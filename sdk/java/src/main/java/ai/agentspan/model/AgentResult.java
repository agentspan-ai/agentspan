// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import ai.agentspan.enums.AgentStatus;
import ai.agentspan.internal.JsonMapper;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * The result of a completed agent execution.
 */
public class AgentResult {
    private final Object output;
    private final String workflowId;
    private final AgentStatus status;
    private final List<Map<String, Object>> toolCalls;
    private final List<AgentEvent> events;
    private final TokenUsage tokenUsage;
    private final String error;

    public AgentResult(
            Object output,
            String workflowId,
            AgentStatus status,
            List<Map<String, Object>> toolCalls,
            List<AgentEvent> events,
            TokenUsage tokenUsage,
            String error) {
        this.output = output;
        this.workflowId = workflowId != null ? workflowId : "";
        this.status = status != null ? status : AgentStatus.COMPLETED;
        this.toolCalls = toolCalls != null ? toolCalls : new ArrayList<>();
        this.events = events != null ? events : new ArrayList<>();
        this.tokenUsage = tokenUsage;
        this.error = error;
    }

    public Object getOutput() { return output; }
    public String getWorkflowId() { return workflowId; }
    public AgentStatus getStatus() { return status; }
    public List<Map<String, Object>> getToolCalls() { return toolCalls; }
    public List<AgentEvent> getEvents() { return events; }
    public TokenUsage getTokenUsage() { return tokenUsage; }
    public String getError() { return error; }

    /** Returns true if the agent completed successfully. */
    public boolean isSuccess() {
        return status == AgentStatus.COMPLETED;
    }

    /**
     * Convert the output to the given type using Jackson.
     *
     * <p>Handles structured output from the server, which may be wrapped in a
     * {@code {"result": ...}} envelope or returned as a flat JSON string.
     *
     * @param cls the target class
     * @param <T> the target type
     * @return the output converted to the given type, or null if conversion fails
     */
    @SuppressWarnings("unchecked")
    public <T> T getOutput(Class<T> cls) {
        if (output == null) return null;
        ObjectMapper mapper = JsonMapper.get();

        Object target = output;

        // Unwrap {"result": ...} envelope if the map has a "result" key
        // (server may also include other metadata keys like "finishReason")
        if (target instanceof Map) {
            Map<String, Object> m = (Map<String, Object>) target;
            if (m.containsKey("result")) {
                Object inner = m.get("result");
                if (inner != null) target = inner;
            }
        }

        // If target is already the right type, return it
        if (cls.isInstance(target)) {
            return cls.cast(target);
        }

        // Serialize to JSON string, then deserialize to the target class
        try {
            String json;
            if (target instanceof String) {
                json = (String) target;
            } else {
                json = mapper.writeValueAsString(target);
            }
            return mapper.readValue(json, cls);
        } catch (Exception e) {
            throw new RuntimeException("Failed to deserialize output to " + cls.getSimpleName(), e);
        }
    }

    /**
     * Pretty-print the agent result to stdout.
     */
    public void printResult() {
        String line = "=".repeat(50);
        System.out.println();
        System.out.println("+" + line + "+");
        System.out.println("| Agent Output" + " ".repeat(37) + "|");
        System.out.println("+" + line + "+");
        System.out.println();

        if (status != AgentStatus.COMPLETED && error != null) {
            System.out.println("ERROR: " + error);
            System.out.println();
        } else if (output instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> outputMap = (Map<String, Object>) output;
            Object result = outputMap.get("result");
            if (result != null) {
                System.out.println(result);
                System.out.println();
            } else {
                for (Map.Entry<String, Object> entry : outputMap.entrySet()) {
                    System.out.println("--- " + entry.getKey() + " ---");
                    System.out.println(entry.getValue());
                    System.out.println();
                }
            }
        } else if (output != null) {
            System.out.println(output);
            System.out.println();
        }

        if (!toolCalls.isEmpty()) {
            System.out.println("Tool calls: " + toolCalls.size());
        }
        if (tokenUsage != null) {
            System.out.println("Tokens: " + tokenUsage.getTotalTokens() + " total ("
                    + tokenUsage.getPromptTokens() + " prompt, "
                    + tokenUsage.getCompletionTokens() + " completion)");
        } else {
            System.out.println("Tokens: -");
        }
        System.out.println("Status: " + status);
        if (!workflowId.isEmpty()) {
            System.out.println("Workflow ID: " + workflowId);
        }
        System.out.println();
    }
}
