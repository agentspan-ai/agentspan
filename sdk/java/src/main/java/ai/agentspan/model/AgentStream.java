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

    private final String executionId;
    private final SseClient sseClient;
    private final HttpApi httpApi;
    private final List<AgentEvent> capturedEvents = new ArrayList<>();
    private AgentResult result;
    private boolean exhausted = false;

    public AgentStream(String executionId, SseClient sseClient, HttpApi httpApi) {
        this.executionId = executionId;
        this.sseClient = sseClient;
        this.httpApi = httpApi;
    }

    public String getExecutionId() {
        return executionId;
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
     * Poll the server until the workflow reaches a terminal status, then return
     * the result.
     *
     * <p>Use this instead of {@link #getResult()} when the original SSE stream
     * may not deliver downstream events — most commonly after a HITL
     * approve/reject, where the resumed sub-execution emits its
     * {@code TOOL_RESULT}/{@code DONE} events on a separate SSE channel and
     * the original stream's blocking {@code nextEvent()} would wait until the
     * HttpClient request times out (~10 min).
     *
     * <p>Status is read from the server's view of the workflow
     * ({@code /api/agent/{id}/status}); previously-captured SSE events are
     * preserved on the returned {@link AgentResult}.
     *
     * @param timeoutMs       maximum wait time in milliseconds
     * @param pollIntervalMs  polling interval in milliseconds
     * @return the agent result reflecting the server's terminal status
     * @throws RuntimeException if the poll deadline is hit before the workflow
     *         reaches a terminal status
     */
    public AgentResult waitForResult(long timeoutMs, long pollIntervalMs) {
        long start = System.currentTimeMillis();
        while (System.currentTimeMillis() - start < timeoutMs) {
            try {
                Map<String, Object> status = httpApi.getAgentStatus(executionId);
                String workflowStatus = (String) status.get("status");
                if (workflowStatus != null && isTerminalStatus(workflowStatus)) {
                    result = buildResultFromStatus(status, workflowStatus);
                    return result;
                }
                Thread.sleep(pollIntervalMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RuntimeException("Interrupted while waiting for stream result", e);
            } catch (Exception e) {
                logger.debug("Error polling stream status for {}: {}", executionId, e.getMessage());
                try {
                    Thread.sleep(pollIntervalMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException("Interrupted while waiting for stream result", ie);
                }
            }
        }
        throw new RuntimeException(
            "Timed out after " + timeoutMs + "ms waiting for stream result: " + executionId);
    }

    private static boolean isTerminalStatus(String status) {
        return "COMPLETED".equals(status)
            || "FAILED".equals(status)
            || "TERMINATED".equals(status)
            || "TIMED_OUT".equals(status);
    }

    @SuppressWarnings("unchecked")
    private AgentResult buildResultFromStatus(Map<String, Object> statusResponse, String workflowStatus) {
        Object output = statusResponse.get("output");
        if (output == null) output = statusResponse.get("result");

        AgentStatus status;
        try {
            status = AgentStatus.valueOf(workflowStatus);
        } catch (IllegalArgumentException e) {
            status = AgentStatus.FAILED;
        }

        String error = null;
        if (status != AgentStatus.COMPLETED) {
            error = (String) statusResponse.get("reasonForIncompletion");
            if (error == null) error = (String) statusResponse.get("error");
        }

        if (output == null) {
            output = java.util.Collections.singletonMap("result", (Object) null);
        } else if (!(output instanceof Map)) {
            output = java.util.Collections.singletonMap("result", output);
        }

        return new AgentResult(
            output, executionId, status,
            new ArrayList<>(), new ArrayList<>(capturedEvents),
            null, error);
    }

    /**
     * Approve a pending HUMAN task on the <b>top-level</b> workflow.
     *
     * <p>This targets the execution id from {@link #getExecutionId()} — i.e. the
     * orchestrator/root execution. It is the right method when:
     * <ul>
     *   <li>You are running a single agent (HUMAN task lives at the top level).</li>
     *   <li>Your sub-agent topology routes approvals to a HUMAN task at the top level.</li>
     * </ul>
     *
     * <p>Under {@link ai.agentspan.enums.Strategy#HANDOFF}, {@code SEQUENTIAL}, or
     * {@code PARALLEL} the HUMAN task usually lives in a <b>sub</b>-execution (the
     * sub-agent's own workflow). In that case this method POSTs to the wrong
     * execution id and the server returns HTTP 500 ("No pending HUMAN task found"):
     * use {@link #approve(AgentEvent)} with the {@code WAITING} event instead.
     */
    public void approve() {
        httpApi.respond(executionId, approveBody(null));
    }

    /**
     * Approve the pending HUMAN task associated with the given {@code WAITING} event.
     *
     * <p>Reads the owning execution id from {@link AgentEvent#getExecutionId()} —
     * the sub-execution that emitted the event — and POSTs to it. Use this whenever
     * the HUMAN task may live below the top level (handoff/sequential/parallel).
     *
     * @param event the WAITING event whose pending HUMAN task should be approved
     */
    public void approve(AgentEvent event) {
        httpApi.respond(targetExecutionId(event), approveBody(null));
    }

    /**
     * Reject a pending HUMAN task on the <b>top-level</b> workflow with a reason.
     *
     * @param reason optional rejection reason
     */
    public void reject(String reason) {
        httpApi.respond(executionId, rejectBody(reason));
    }

    /**
     * Reject the pending HUMAN task associated with the given {@code WAITING} event.
     *
     * @param event  the WAITING event whose pending HUMAN task should be rejected
     * @param reason optional rejection reason
     */
    public void reject(AgentEvent event, String reason) {
        httpApi.respond(targetExecutionId(event), rejectBody(reason));
    }

    /**
     * Send a message to the <b>top-level</b> waiting workflow (multi-turn conversation).
     *
     * @param message the message to send
     */
    public void send(String message) {
        java.util.Map<String, Object> body = new java.util.HashMap<>();
        body.put("message", message);
        httpApi.respond(executionId, body);
    }

    /**
     * Send a message to the waiting execution associated with the given event.
     *
     * @param event   the WAITING event identifying the execution to send to
     * @param message the message to send
     */
    public void send(AgentEvent event, String message) {
        java.util.Map<String, Object> body = new java.util.HashMap<>();
        body.put("message", message);
        httpApi.respond(targetExecutionId(event), body);
    }

    private static java.util.Map<String, Object> approveBody(String reason) {
        java.util.Map<String, Object> body = new java.util.HashMap<>();
        body.put("approved", true);
        if (reason != null && !reason.isEmpty()) body.put("reason", reason);
        return body;
    }

    private static java.util.Map<String, Object> rejectBody(String reason) {
        java.util.Map<String, Object> body = new java.util.HashMap<>();
        body.put("approved", false);
        if (reason != null && !reason.isEmpty()) body.put("reason", reason);
        return body;
    }

    private static String targetExecutionId(AgentEvent event) {
        if (event == null) {
            throw new IllegalArgumentException("event must not be null");
        }
        String id = event.getExecutionId();
        if (id == null || id.isEmpty()) {
            throw new IllegalArgumentException("event has no execution id");
        }
        return id;
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

        return new AgentResult(output, executionId, status, toolCalls, new ArrayList<>(capturedEvents), null, error);
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
