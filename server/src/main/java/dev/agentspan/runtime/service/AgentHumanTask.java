/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.core.execution.tasks.WorkflowSystemTask;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import dev.agentspan.runtime.model.AgentSSEEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.Map;

import static com.netflix.conductor.common.metadata.tasks.TaskType.TASK_TYPE_HUMAN;

/**
 * Custom HUMAN task that emits a WAITING SSE event immediately when started.
 *
 * <p>Conductor's default {@code Human} task sets status to IN_PROGRESS but
 * does NOT call {@code TaskStatusListener.onTaskScheduled/onTaskInProgress}
 * for system tasks.  This override hooks into {@code start()} to emit the
 * SSE event directly.</p>
 *
 * <p>Registered as a {@code @Primary} bean via {@link AgentHumanTaskConfig}.</p>
 */
public class AgentHumanTask extends WorkflowSystemTask {

    private static final Logger logger = LoggerFactory.getLogger(AgentHumanTask.class);

    private final AgentStreamRegistry streamRegistry;

    public AgentHumanTask(AgentStreamRegistry streamRegistry) {
        super(TASK_TYPE_HUMAN);
        this.streamRegistry = streamRegistry;
        logger.debug("AgentHumanTask registered (overrides default HUMAN with SSE support)");
    }

    @Override
    public void start(WorkflowModel workflow, TaskModel task, WorkflowExecutor workflowExecutor) {
        task.setStatus(TaskModel.Status.IN_PROGRESS);

        // Emit WAITING event immediately
        String wfId = workflow.getWorkflowId();
        String taskRef = task.getReferenceTaskName();
        Map<String, Object> pendingTool = new HashMap<>();
        Map<String, Object> input = task.getInputData();
        if (input != null) {
            pendingTool.put("tool_name", input.get("tool_name"));
            pendingTool.put("parameters", input.get("parameters"));
        }
        pendingTool.put("taskRefName", taskRef);

        try {
            streamRegistry.send(wfId, AgentSSEEvent.waiting(wfId, pendingTool));
            logger.debug("Emitted WAITING event for HUMAN task {} in workflow {}", taskRef, wfId);
        } catch (Exception e) {
            logger.warn("Failed to emit WAITING event for workflow {}: {}", wfId, e.getMessage());
        }
    }

    @Override
    public void cancel(WorkflowModel workflow, TaskModel task, WorkflowExecutor workflowExecutor) {
        task.setStatus(TaskModel.Status.CANCELED);
    }
}
