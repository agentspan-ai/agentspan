// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.model;

import ai.agentspan.enums.AgentStatus;
import ai.agentspan.internal.HttpApi;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * A handle to a running agent workflow.
 *
 * <p>Returned by {@link ai.agentspan.AgentRuntime#start(ai.agentspan.Agent, String)}.
 * Allows checking status, interacting with human-in-the-loop pauses, and controlling
 * execution — from any process, even after restarts.
 */
public class AgentHandle {
    private static final Logger logger = LoggerFactory.getLogger(AgentHandle.class);

    private static final long DEFAULT_POLL_INTERVAL_MS = 2000;
    private static final long DEFAULT_TIMEOUT_MS = 600_000; // 10 minutes

    private final String workflowId;
    private final HttpApi httpApi;

    public AgentHandle(String workflowId, HttpApi httpApi) {
        this.workflowId = workflowId;
        this.httpApi = httpApi;
    }

    public String getWorkflowId() {
        return workflowId;
    }

    /**
     * Poll the server until the agent completes and return the final result.
     *
     * @return the agent result
     * @throws RuntimeException if the agent fails or times out
     */
    public AgentResult waitForResult() {
        return waitForResult(DEFAULT_TIMEOUT_MS, DEFAULT_POLL_INTERVAL_MS);
    }

    /**
     * Poll the server until the agent completes with explicit timeout.
     *
     * @param timeoutMs       maximum wait time in milliseconds
     * @param pollIntervalMs  polling interval in milliseconds
     * @return the agent result
     */
    @SuppressWarnings("unchecked")
    public AgentResult waitForResult(long timeoutMs, long pollIntervalMs) {
        long startTime = System.currentTimeMillis();

        while (System.currentTimeMillis() - startTime < timeoutMs) {
            try {
                Map<String, Object> status = httpApi.getAgentStatus(workflowId);
                String workflowStatus = (String) status.get("status");

                if (workflowStatus == null) {
                    logger.debug("Waiting for agent {} — status unknown", workflowId);
                } else if (isTerminalStatus(workflowStatus)) {
                    return buildResult(status, workflowStatus);
                } else {
                    logger.debug("Waiting for agent {} — status: {}", workflowId, workflowStatus);
                }

                Thread.sleep(pollIntervalMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new RuntimeException("Interrupted while waiting for agent result", e);
            } catch (Exception e) {
                logger.error("Error polling agent status: {}", e.getMessage());
                try {
                    Thread.sleep(pollIntervalMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException("Interrupted while waiting for agent result", ie);
                }
            }
        }

        throw new RuntimeException("Agent timed out after " + timeoutMs + "ms: " + workflowId);
    }

    /**
     * Approve a pending tool call that requires human approval.
     */
    public void approve() {
        httpApi.respondToAgent(workflowId, true, null);
    }

    /**
     * Reject a pending tool call with an optional reason.
     *
     * @param reason rejection reason
     */
    public void reject(String reason) {
        httpApi.respondToAgent(workflowId, false, reason);
    }

    /**
     * Send an arbitrary structured response to a waiting workflow.
     *
     * <p>Use this for MANUAL agent selection:
     * <pre>{@code handle.respond(Map.of("selected", "writer")); }</pre>
     *
     * @param data the response payload
     */
    public void respond(Map<String, Object> data) {
        httpApi.respondWithData(workflowId, data);
    }

    /**
     * Send a message to a waiting agent.
     *
     * @param message the message to send
     */
    public void send(String message) {
        httpApi.respondToAgent(workflowId, true, null);
    }

    /**
     * Check whether the workflow is currently paused waiting for human input.
     *
     * @return true if the server reports isWaiting == true
     */
    public boolean isWaiting() {
        try {
            Map<String, Object> status = httpApi.getAgentStatus(workflowId);
            Object waiting = status.get("isWaiting");
            return Boolean.TRUE.equals(waiting);
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Poll until the workflow is waiting for human input or reaches a terminal state.
     *
     * @param timeoutMs maximum wait time in milliseconds
     * @return true if the workflow is now waiting, false if it completed/failed first
     */
    public boolean waitUntilWaiting(long timeoutMs) {
        long start = System.currentTimeMillis();
        while (System.currentTimeMillis() - start < timeoutMs) {
            try {
                Map<String, Object> status = httpApi.getAgentStatus(workflowId);
                Object waiting = status.get("isWaiting");
                if (Boolean.TRUE.equals(waiting)) return true;
                String workflowStatus = (String) status.get("status");
                if (workflowStatus != null && isTerminalStatus(workflowStatus)) return false;
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            } catch (Exception e) {
                try { Thread.sleep(1000); } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt(); return false;
                }
            }
        }
        return false;
    }

    private boolean isTerminalStatus(String status) {
        return "COMPLETED".equals(status)
            || "FAILED".equals(status)
            || "TERMINATED".equals(status)
            || "TIMED_OUT".equals(status);
    }

    @SuppressWarnings("unchecked")
    private AgentResult buildResult(Map<String, Object> statusResponse, String workflowStatus) {
        Object output = statusResponse.get("output");
        if (output == null) {
            output = statusResponse.get("result");
        }

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

        // Normalize output to a map
        if (output == null) {
            output = java.util.Collections.singletonMap("result", (Object) null);
        } else if (!(output instanceof Map)) {
            output = java.util.Collections.singletonMap("result", output);
        }

        // Token usage + tool calls: the server doesn't aggregate either on the
        // workflow status response, but every LLM_CHAT_COMPLETE task carries
        // tokenUsed/promptTokens/completionTokens in its outputData, and every
        // tool-worker SIMPLE task in the workflow corresponds to one LLM tool
        // call. Walk the workflow tasks once and aggregate both.
        TokenUsage tokenUsage = null;
        List<Map<String, Object>> toolCalls = new ArrayList<>();
        try {
            Map<String, Object> workflow = httpApi.getWorkflow(workflowId);
            Object tasksRaw = workflow.get("tasks");
            if (tasksRaw instanceof List) {
                int promptT = 0, completionT = 0, totalT = 0;
                boolean sawTokens = false;
                for (Object taskObj : (List<Object>) tasksRaw) {
                    if (!(taskObj instanceof Map)) continue;
                    Map<String, Object> task = (Map<String, Object>) taskObj;
                    String taskType = (String) task.get("taskType");
                    Map<String, Object> outputData = (Map<String, Object>) task.get("outputData");

                    // LLM task — aggregate tokens
                    if ("LLM_CHAT_COMPLETE".equals(taskType) && outputData != null) {
                        promptT     += toInt(outputData.get("promptTokens"));
                        completionT += toInt(outputData.get("completionTokens"));
                        totalT      += toInt(outputData.get("tokenUsed"));
                        sawTokens = true;
                        continue;
                    }

                    // Tool worker task — capture name, input args (stripping
                    // internal Agentspan context), and output result.
                    // Server uses SIMPLE for workers, but the taskType field on
                    // the task instance is the worker name itself (e.g. "add").
                    // We treat any non-system task whose name appears in the
                    // task definition as a worker tool call.
                    String refName = (String) task.get("referenceTaskName");
                    if (refName != null
                        && refName.startsWith("call_")
                        && outputData != null) {
                        Map<String, Object> tc = new LinkedHashMap<>();
                        tc.put("name", taskType);
                        Map<String, Object> inputData = (Map<String, Object>) task.get("inputData");
                        if (inputData != null) {
                            Map<String, Object> cleaned = new LinkedHashMap<>();
                            for (Map.Entry<String, Object> e : inputData.entrySet()) {
                                String k = e.getKey();
                                if (k.startsWith("_")
                                    || "method".equals(k)
                                    || "__agentspan_ctx__".equals(k)
                                    || "evaluatorType".equals(k)
                                    || "expression".equals(k)
                                    || "ctx".equals(k)
                                    || "workerTag".equals(k)
                                    || "agentConfig".equals(k)) continue;
                                cleaned.put(k, e.getValue());
                            }
                            tc.put("args", cleaned);
                        }
                        tc.put("result", outputData.get("result"));
                        toolCalls.add(tc);
                    }
                }
                if (sawTokens) {
                    tokenUsage = new TokenUsage(promptT, completionT, totalT);
                }
            }
        } catch (Exception e) {
            logger.debug("Could not extract tokens/toolCalls for {}: {}", workflowId, e.getMessage());
        }

        return new AgentResult(output, workflowId, status, toolCalls, null, tokenUsage, error);
    }

    private int toInt(Object value) {
        if (value == null) return 0;
        if (value instanceof Number) return ((Number) value).intValue();
        try {
            return Integer.parseInt(value.toString());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    @Override
    public String toString() {
        return "AgentHandle{workflowId=" + workflowId + "}";
    }
}
