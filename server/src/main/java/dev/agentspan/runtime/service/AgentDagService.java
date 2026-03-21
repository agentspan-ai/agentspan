/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.core.exception.NotFoundException;
import com.netflix.conductor.dao.ExecutionDAO;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;
import dev.agentspan.runtime.model.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class AgentDagService {

    private final ExecutionDAO executionDAO;

    public InjectTaskResponse injectTask(String workflowId, InjectTaskRequest req) {
        WorkflowModel workflow = executionDAO.getWorkflow(workflowId, true);
        if (workflow == null) {
            // NotFoundException is mapped to HTTP 404 by Conductor's ApplicationExceptionMapper
            throw new NotFoundException("Workflow not found: " + workflowId);
        }

        TaskModel task = new TaskModel();
        task.setTaskId(UUID.randomUUID().toString());
        task.setTaskDefName(req.getTaskDefName());
        task.setReferenceTaskName(req.getReferenceTaskName());
        task.setTaskType(req.getType());
        task.setStatus(TaskModel.Status.IN_PROGRESS);
        task.setWorkflowInstanceId(workflowId);
        task.setWorkflowType(workflow.getWorkflowName());
        task.setInputData(req.getInputData() != null ? req.getInputData() : Collections.emptyMap());
        task.setSeq(workflow.getTasks().size() + 1);
        long now = System.currentTimeMillis();
        task.setScheduledTime(now);
        task.setStartTime(now);

        if (req.getSubWorkflowParam() != null) {
            task.setSubWorkflowId(req.getSubWorkflowParam().getWorkflowId());
        }

        executionDAO.createTasks(List.of(task));
        return new InjectTaskResponse(task.getTaskId());
    }

    public CreateTrackingWorkflowResponse createTrackingWorkflow(CreateTrackingWorkflowRequest req) {
        WorkflowDef def = new WorkflowDef();
        def.setName(req.getWorkflowName());
        def.setVersion(1);
        def.setTasks(Collections.emptyList());
        def.setInputParameters(List.of("prompt"));

        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId(UUID.randomUUID().toString());
        workflow.setWorkflowDefinition(def);
        workflow.setStatus(WorkflowModel.Status.RUNNING);
        workflow.setInput(req.getInput());
        workflow.setCreateTime(System.currentTimeMillis());

        executionDAO.createWorkflow(workflow);
        return new CreateTrackingWorkflowResponse(workflow.getWorkflowId());
    }
}
