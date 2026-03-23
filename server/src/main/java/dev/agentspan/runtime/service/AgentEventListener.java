/*
 * Copyright (c) 2025 Agentspan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import com.netflix.conductor.core.listener.TaskStatusListener;
import com.netflix.conductor.core.listener.WorkflowStatusListener;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import dev.agentspan.runtime.credentials.CredentialResolutionService;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import dev.agentspan.runtime.model.AgentSSEEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/**
 * Listens to Conductor task/workflow state changes and translates them into
 * {@link AgentSSEEvent}s pushed to connected SSE clients via
 * {@link AgentStreamRegistry}.
 *
 * <p>Overrides Conductor's default stub listeners via {@code @Primary}.</p>
 */
@Component
@Primary
public class AgentEventListener implements TaskStatusListener, WorkflowStatusListener {

    private static final Logger logger = LoggerFactory.getLogger(AgentEventListener.class);

    private final AgentStreamRegistry streamRegistry;

    @Autowired(required = false)
    private ExecutionTokenService executionTokenService;

    @Autowired(required = false)
    private CredentialResolutionService credentialResolutionService;

    @Autowired
    public AgentEventListener(AgentStreamRegistry streamRegistry) {
        this.streamRegistry = streamRegistry;
        logger.info("AgentEventListener active (TaskStatusListener + WorkflowStatusListener)");
    }

    /** Package-private constructor for testing with token revocation. */
    AgentEventListener(AgentStreamRegistry streamRegistry, ExecutionTokenService tokenService) {
        this.streamRegistry = streamRegistry;
        this.executionTokenService = tokenService;
    }

    // ── TaskStatusListener ───────────────────────────────────────────

    @Override
    public void onTaskScheduled(TaskModel task) {
        String wfId = task.getWorkflowInstanceId();
        String taskType = task.getTaskType();
        String taskRef = task.getReferenceTaskName();
        logger.debug("onTaskScheduled: wfId={}, type={}, ref={}", wfId, taskType, taskRef);

        // Resolve ${NAME} credential placeholders in MCP task headers
        if ("CALL_MCP_TOOL".equals(taskType)) {
            resolveMcpCredentialHeaders(task);
        }

        if ("LLM_CHAT_COMPLETE".equals(taskType)) {
            emit(wfId, AgentSSEEvent.thinking(wfId, taskRef));
        } else if ("SUB_WORKFLOW".equals(taskType)) {
            // Register child workflow alias for event forwarding
            String childWfId = task.getSubWorkflowId();
            if (childWfId != null && !childWfId.isEmpty()) {
                streamRegistry.registerAlias(childWfId, wfId);
            }
            String target = extractHandoffTarget(taskRef);
            emit(wfId, AgentSSEEvent.handoff(wfId, target));
        }
        // Note: HUMAN tasks emit WAITING via AgentHumanTask.start(), not here.
        // Conductor does NOT call TaskStatusListener for system tasks.
    }

    @Override
    public void onTaskInProgress(TaskModel task) {
        // HUMAN tasks are handled by AgentHumanTask.start() directly.
        // This callback is not called for system tasks by Conductor.
        logger.debug("onTaskInProgress: wfId={}, type={}, ref={}",
                task.getWorkflowInstanceId(), task.getTaskType(), task.getReferenceTaskName());
    }

    @Override
    public void onTaskCompleted(TaskModel task) {
        String wfId = task.getWorkflowInstanceId();
        String taskRef = task.getReferenceTaskName();
        logger.debug("onTaskCompleted: wfId={}, type={}, ref={}", wfId, task.getTaskType(), taskRef);
        Map<String, Object> output = task.getOutputData();
        if (output == null) output = Map.of();

        // Tool dispatch — SIMPLE tasks that are tool invocations
        if (isToolTask(task)) {
            String toolName = resolveToolName(task);
            Object args = task.getInputData();
            Object result = output.get("result");
            if (result == null) result = output;
            emit(wfId, AgentSSEEvent.toolCall(wfId, toolName, args));
            emit(wfId, AgentSSEEvent.toolResult(wfId, toolName, result));
        }
        // Guardrail tasks — identified by "guardrail" in ref name
        else if (taskRef != null && taskRef.contains("guardrail") && output.containsKey("passed")) {
            Boolean passed = (Boolean) output.get("passed");
            String name = taskRef;
            if (Boolean.TRUE.equals(passed)) {
                emit(wfId, AgentSSEEvent.guardrailPass(wfId, name));
            } else {
                String message = (String) output.getOrDefault("message", "");
                emit(wfId, AgentSSEEvent.guardrailFail(wfId, name, message));
            }
        }
    }

    @Override
    public void onTaskFailed(TaskModel task) {
        String wfId = task.getWorkflowInstanceId();
        String reason = task.getReasonForIncompletion();
        logger.info("onTaskFailed: wfId={}, ref={}, reason={}", wfId, task.getReferenceTaskName(), reason);
        emit(wfId, AgentSSEEvent.error(wfId, task.getReferenceTaskName(), reason));
    }

    @Override
    public void onTaskCanceled(TaskModel task) {
        // No SSE event needed
    }

    @Override
    public void onTaskFailedWithTerminalError(TaskModel task) {
        onTaskFailed(task);
    }

    @Override
    public void onTaskTimedOut(TaskModel task) {
        String wfId = task.getWorkflowInstanceId();
        emit(wfId, AgentSSEEvent.error(wfId, task.getReferenceTaskName(), "Task timed out"));
    }

    @Override
    public void onTaskCompletedWithErrors(TaskModel task) {
        // Treat as normal completion for SSE purposes
        onTaskCompleted(task);
    }

    @Override
    public void onTaskSkipped(TaskModel task) {
        // No SSE event needed
    }

    // ── WorkflowStatusListener ───────────────────────────────────────

    @Override
    public void onWorkflowCompleted(WorkflowModel workflow) {
        // Called by Conductor for non-IfEnabled path (rarely used)
        handleWorkflowCompleted(workflow);
    }

    @Override
    public void onWorkflowTerminated(WorkflowModel workflow) {
        // Called by Conductor for non-IfEnabled path (rarely used)
        handleWorkflowTerminated(workflow);
    }

    // The *IfEnabled variants are the PRIMARY callback path used by
    // WorkflowExecutorOps.notifyWorkflowStatusListener()

    @Override
    public void onWorkflowCompletedIfEnabled(WorkflowModel workflow) {
        handleWorkflowCompleted(workflow);
    }

    @Override
    public void onWorkflowTerminatedIfEnabled(WorkflowModel workflow) {
        handleWorkflowTerminated(workflow);
    }

    @Override
    public void onWorkflowFinalizedIfEnabled(WorkflowModel workflow) {
        // No SSE event needed
    }

    @Override
    public void onWorkflowStartedIfEnabled(WorkflowModel workflow) {
        // No SSE event — client already knows (they started it)
    }

    @Override
    public void onWorkflowPausedIfEnabled(WorkflowModel workflow) {
        String wfId = workflow.getWorkflowId();
        logger.debug("onWorkflowPaused: wfId={}", wfId);
        emit(wfId, AgentSSEEvent.waiting(wfId, Map.of()));
    }

    @Override
    public void onWorkflowResumedIfEnabled(WorkflowModel workflow) {
        // No SSE event needed
    }

    private void handleWorkflowCompleted(WorkflowModel workflow) {
        String wfId = workflow.getWorkflowId();
        logger.info("onWorkflowCompleted: wfId={}", wfId);
        Map<String, Object> output = workflow.getOutput();
        emit(wfId, AgentSSEEvent.done(wfId, output));
        if (executionTokenService != null) {
            revokeWorkflowToken(workflow);
        }
        streamRegistry.complete(wfId);
    }

    private void handleWorkflowTerminated(WorkflowModel workflow) {
        String wfId = workflow.getWorkflowId();
        logger.info("onWorkflowTerminated: wfId={}, reason={}", wfId, workflow.getReasonForIncompletion());
        String reason = workflow.getReasonForIncompletion();
        emit(wfId, AgentSSEEvent.error(wfId, "workflow", reason != null ? reason : "Workflow terminated"));
        if (executionTokenService != null) {
            revokeWorkflowToken(workflow);
        }
        streamRegistry.complete(wfId);
    }

    private void revokeWorkflowToken(WorkflowModel workflow) {
        try {
            Object ctx = workflow.getVariables() != null
                ? workflow.getVariables().get("__agentspan_ctx__") : null;
            if (!(ctx instanceof Map)) return;
            Object tokenObj = ((Map<?, ?>) ctx).get("execution_token");
            if (!(tokenObj instanceof String token)) return;
            ExecutionTokenService.TokenPayload payload = executionTokenService.validate(token);
            executionTokenService.revoke(payload.jti(), payload.exp());
            logger.info("Execution token revoked for terminated workflow {}", workflow.getWorkflowId());
        } catch (Exception e) {
            logger.debug("Could not revoke execution token for workflow {}: {}",
                workflow.getWorkflowId(), e.getMessage());
        }
    }

    // ── Internal ─────────────────────────────────────────────────────

    /**
     * Resolve ${NAME} credential placeholders in CALL_MCP_TOOL task headers.
     * MCP is a worker task (not a system task), so we resolve before the worker picks it up.
     */
    @SuppressWarnings("unchecked")
    private void resolveMcpCredentialHeaders(TaskModel task) {
        if (executionTokenService == null || credentialResolutionService == null) return;

        Map<String, Object> input = task.getInputData();
        Object headers = input.get("headers");
        Object ctx = input.get("__agentspan_ctx__");

        if (!(headers instanceof Map<?,?> headerMap) || ctx == null) return;

        // Check for ${NAME} patterns
        boolean hasPlaceholders = false;
        java.util.regex.Pattern p = java.util.regex.Pattern.compile("\\$\\{(\\w+)}");
        for (Object v : headerMap.values()) {
            if (v != null && p.matcher(String.valueOf(v)).find()) {
                hasPlaceholders = true;
                break;
            }
        }
        if (!hasPlaceholders) return;

        // Extract userId from execution token
        String token = null;
        if (ctx instanceof Map<?,?> ctxMap) {
            token = (String) ctxMap.get("execution_token");
        } else if (ctx instanceof String s) {
            token = s;
        }
        if (token == null) return;

        try {
            String userId = executionTokenService.validate(token).userId();
            Map<String, String> resolved = new java.util.LinkedHashMap<>();
            for (Map.Entry<?,?> entry : headerMap.entrySet()) {
                String value = String.valueOf(entry.getValue());
                java.util.regex.Matcher m = p.matcher(value);
                StringBuilder sb = new StringBuilder();
                while (m.find()) {
                    String credName = m.group(1);
                    String credValue = credentialResolutionService.resolve(userId, credName);
                    m.appendReplacement(sb, java.util.regex.Matcher.quoteReplacement(
                        credValue != null ? credValue : ""));
                }
                m.appendTail(sb);
                resolved.put(String.valueOf(entry.getKey()), sb.toString());
            }
            input.put("headers", resolved);
        } catch (Exception e) {
            logger.warn("Failed to resolve MCP credential headers: {}", e.getMessage());
        }
    }

    private void emit(String workflowId, AgentSSEEvent event) {
        try {
            streamRegistry.send(workflowId, event);
        } catch (Exception e) {
            logger.warn("Failed to emit SSE event for workflow {}: {}", workflowId, e.getMessage());
        }
    }

    /**
     * Determine if a completed task is a tool invocation (not an internal
     * system task like SWITCH, DO_WHILE, INLINE, etc.).
     */
    private boolean isToolTask(TaskModel task) {
        String taskType = task.getTaskType();
        if (taskType == null) return false;
        // Skip framework passthrough wrapper tasks — they emit their own fine-grained events
        if (task.getReferenceTaskName() != null && task.getReferenceTaskName().startsWith("_fw_")) {
            return false;
        }
        // System task types that are NOT tool invocations
        switch (taskType) {
            case "LLM_CHAT_COMPLETE":
            case "SWITCH":
            case "DO_WHILE":
            case "INLINE":
            case "SET_VARIABLE":
            case "FORK_JOIN_DYNAMIC":
            case "JOIN":
            case "SUB_WORKFLOW":
            case "HUMAN":
            case "TERMINATE":
            case "HTTP":
            case "CALL_MCP_TOOL":
                return false;
            default:
                // SIMPLE or other user-defined task types = tool invocation
                return "SIMPLE".equals(taskType) || task.getTaskDefinition().isPresent();
        }
    }

    /**
     * Resolve the actual tool/function name from a task.
     *
     * <p>Server-compiled workflows use SIMPLE tasks where the actual tool name
     * is stored in {@code inputData.method} (set by the enrichment script).
     * Locally-compiled workflows use SIMPLE tasks with a dispatch pattern
     * where the function name is stored in the output data.
     * SDK-compiled worker tasks use a custom task type matching the function name.</p>
     */
    private String resolveToolName(TaskModel task) {
        String taskType = task.getTaskType();

        // Server-compiled SIMPLE tasks: tool name is in inputData.method
        Map<String, Object> input = task.getInputData();
        if (input != null && input.containsKey("method")) {
            return String.valueOf(input.get("method"));
        }

        // Locally-compiled (dispatch): function name in output data
        Map<String, Object> output = task.getOutputData();
        if (output != null && output.containsKey("function")) {
            return String.valueOf(output.get("function"));
        }

        // SDK-compiled workers: taskType is the function name (e.g. "get_weather")
        if (!"SIMPLE".equals(taskType) && taskType != null) {
            return taskType.toLowerCase();
        }

        // Fallback to task reference name
        return task.getReferenceTaskName();
    }

    /**
     * Extract the target agent name from a sub-workflow task reference.
     *
     * <p>Conductor generates indexed references for sub-workflows in
     * multi-agent strategies.  Examples:</p>
     * <ul>
     *   <li>{@code 0_billing__1}             → {@code billing}</li>
     *   <li>{@code analysis_parallel_0_pros_analyst} → {@code pros_analyst}</li>
     *   <li>{@code debate_round_robin_1_optimist__1} → {@code optimist}</li>
     *   <li>{@code researcher_writer_step_0_researcher} → {@code researcher}</li>
     *   <li>{@code support_handoff_billing}   → {@code billing}</li>
     * </ul>
     *
     * <p>Strategy:</p>
     * <ol>
     *   <li>Strip trailing {@code __N} turn counter</li>
     *   <li>If it contains {@code _handoff_}, take everything after</li>
     *   <li>Strip strategy-indexed prefixes ({@code _sequential_N_}, etc.)</li>
     *   <li>Strip {@code _step_N_} sequential pipeline prefixes</li>
     *   <li>Strip leading {@code N_} index prefix</li>
     * </ol>
     */
    private String extractHandoffTarget(String taskRef) {
        if (taskRef == null) return "unknown";

        // Step 1: strip trailing __N (turn counter)
        String name = taskRef.replaceAll("__\\d+$", "");

        // Step 2: strip strategy-indexed prefixes
        // Matches: <parent>_<strategy>_<idx>_<agent_name>
        // Strategies: handoff (handoff+router), agent (round_robin+swarm),
        //   step (sequential), parallel, and others
        java.util.regex.Matcher strategyMatcher = java.util.regex.Pattern.compile(
                "^.+?_(?:handoff|agent|step|sequential|parallel|round_robin|router|swarm|random|manual)_(\\d+)_(.*)"
        ).matcher(name);
        if (strategyMatcher.matches()) {
            return strategyMatcher.group(2);
        }

        // Step 3: strip leading N_ index prefix (e.g. "0_billing")
        java.util.regex.Matcher idxMatcher = java.util.regex.Pattern.compile(
                "^\\d+_(.*)"
        ).matcher(name);
        if (idxMatcher.matches()) {
            return idxMatcher.group(1);
        }

        return name;
    }
}
