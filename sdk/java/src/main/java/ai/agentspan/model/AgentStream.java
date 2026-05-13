// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.model;

import ai.agentspan.enums.AgentStatus;
import ai.agentspan.enums.EventType;
import ai.agentspan.internal.HttpApi;
import ai.agentspan.internal.SseClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

/**
 * A streaming view of an agent execution.
 *
 * <p>Iterable — yields {@link AgentEvent} objects as they arrive via SSE.
 * After iteration, {@link #getResult()} returns a summary {@link AgentResult}.
 *
 * <p>Also exposes HITL convenience methods (approve/reject/send).
 *
 * <p>Example:
 * <pre>{@code
 * AgentStream stream = runtime.stream(agent, "Tell me a story");
 * for (AgentEvent event : stream) {
 *     System.out.println(event.getType() + ": " + event.getContent());
 * }
 * AgentResult result = stream.getResult();
 * }</pre>
 */
public class AgentStream implements Iterable<AgentEvent>, AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(AgentStream.class);

    private final String workflowId;
    private final SseClient sseClient;
    private final HttpApi httpApi;
    private final List<AgentEvent> capturedEvents = new ArrayList<>();
    private AgentResult result;
    private boolean exhausted = false;

    public AgentStream(String workflowId, SseClient sseClient, HttpApi httpApi) {
        this.workflowId = workflowId;
        this.sseClient = sseClient;
        this.httpApi = httpApi;
    }

    public String getWorkflowId() {
        return workflowId;
    }

    @Override
    public Iterator<AgentEvent> iterator() {
        return new SseEventIterator();
    }

    /**
     * Drain the stream and return the final result.
     */
    public AgentResult getResult() {
        if (!exhausted) {
            for (AgentEvent event : this) {
                // consume all events
            }
        }
        if (result == null) {
            result = buildResult();
        }
        return result;
    }

    /**
     * Approve a pending tool call that requires human approval.
     */
    public void approve() {
        httpApi.respondToAgent(workflowId, true, null);
    }

    /**
     * Reject a pending tool call with a reason.
     *
     * @param reason optional rejection reason
     */
    public void reject(String reason) {
        httpApi.respondToAgent(workflowId, false, reason);
    }

    /**
     * Send a message to a waiting agent (multi-turn conversation).
     *
     * @param message the message to send
     */
    public void send(String message) {
        // Use the respond endpoint with a message payload
        java.util.Map<String, Object> body = new java.util.HashMap<>();
        body.put("message", message);
        // Delegate to httpApi
        httpApi.respondToAgent(workflowId, true, null);
    }

    @Override
    public void close() {
        if (sseClient != null) {
            sseClient.close();
        }
    }

    private AgentResult buildResult() {
        Object output = null;
        AgentStatus status = AgentStatus.COMPLETED;
        String error = null;
        List<Map<String, Object>> toolCalls = new ArrayList<>();
        Map<String, Object> pendingCall = null;

        for (AgentEvent event : capturedEvents) {
            EventType type = event.getType();
            if (type == EventType.TOOL_CALL) {
                pendingCall = new java.util.LinkedHashMap<>();
                pendingCall.put("name", event.getToolName());
                pendingCall.put("args", event.getArgs());
            } else if (type == EventType.TOOL_RESULT) {
                if (pendingCall != null) {
                    pendingCall.put("result", event.getResult());
                    toolCalls.add(pendingCall);
                    pendingCall = null;
                } else {
                    Map<String, Object> call = new java.util.LinkedHashMap<>();
                    call.put("name", event.getToolName());
                    call.put("result", event.getResult());
                    toolCalls.add(call);
                }
            } else if (type == EventType.DONE) {
                output = event.getOutput();
            } else if (type == EventType.ERROR) {
                output = event.getContent();
                status = AgentStatus.FAILED;
                error = event.getContent();
            } else if (type == EventType.GUARDRAIL_FAIL) {
                status = AgentStatus.FAILED;
                error = event.getContent();
            }
        }

        // Normalize output
        if (output == null && status == AgentStatus.COMPLETED) {
            output = java.util.Collections.singletonMap("result", (Object) null);
        } else if (!(output instanceof Map)) {
            if (status == AgentStatus.FAILED) {
                Map<String, Object> errMap = new java.util.LinkedHashMap<>();
                errMap.put("error", output != null ? output.toString() : (error != null ? error : "Unknown error"));
                errMap.put("status", "FAILED");
                output = errMap;
            } else {
                output = java.util.Collections.singletonMap("result", output);
            }
        }

        return new AgentResult(output, workflowId, status, toolCalls, new ArrayList<>(capturedEvents), null, error);
    }

    private class SseEventIterator implements Iterator<AgentEvent> {
        private AgentEvent nextEvent = null;
        private boolean done = false;

        @Override
        public boolean hasNext() {
            if (done) return false;
            if (nextEvent != null) return true;

            nextEvent = sseClient.nextEvent();
            if (nextEvent == null) {
                done = true;
                exhausted = true;
                result = buildResult();
                return false;
            }

            capturedEvents.add(nextEvent);
            return true;
        }

        @Override
        public AgentEvent next() {
            if (!hasNext()) {
                throw new NoSuchElementException("No more events");
            }
            AgentEvent event = nextEvent;
            nextEvent = null;
            return event;
        }
    }
}
