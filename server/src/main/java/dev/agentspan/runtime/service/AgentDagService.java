/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.netflix.conductor.common.metadata.workflow.SubWorkflowParams;
import com.netflix.conductor.common.metadata.workflow.WorkflowDef;
import com.netflix.conductor.common.metadata.workflow.WorkflowTask;
import com.netflix.conductor.core.exception.NotFoundException;
import com.netflix.conductor.dao.ExecutionDAO;
import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

import dev.agentspan.runtime.model.*;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class AgentDagService {

    private final ExecutionDAO executionDAO;

    public InjectTaskResponse injectTask(String executionId, InjectTaskRequest req) {
        WorkflowModel workflow = executionDAO.getWorkflow(executionId, true);
        if (workflow == null) {
            // NotFoundException is mapped to HTTP 404 by Conductor's ApplicationExceptionMapper
            throw new NotFoundException("Execution not found: " + executionId);
        }

        TaskModel task = new TaskModel();
        task.setTaskId(UUID.randomUUID().toString());
        task.setTaskDefName(req.getTaskDefName());
        task.setReferenceTaskName(req.getReferenceTaskName());
        task.setTaskType(req.getType());
        task.setStatus(TaskModel.Status.IN_PROGRESS);
        task.setWorkflowInstanceId(executionId);
        task.setWorkflowType(workflow.getWorkflowName());
        task.setInputData(req.getInputData() != null ? req.getInputData() : Collections.emptyMap());
        task.setSeq(workflow.getTasks().size() + 1);
        long now = System.currentTimeMillis();
        task.setScheduledTime(now);
        task.setStartTime(now);

        if (req.getSubWorkflowParam() != null) {
            task.setSubWorkflowId(req.getSubWorkflowParam().getExecutionId());
        }

        executionDAO.createTasks(List.of(task));

        // Add a corresponding WorkflowTask to the definition so the DAG view renders it
        WorkflowTask workflowTask = new WorkflowTask();
        workflowTask.setName(req.getTaskDefName());
        workflowTask.setTaskReferenceName(req.getReferenceTaskName());
        workflowTask.setType(req.getType());
        workflowTask.setInputParameters(req.getInputData() != null ? req.getInputData() : Collections.emptyMap());
        if (req.getSubWorkflowParam() != null) {
            SubWorkflowParams swp = new SubWorkflowParams();
            swp.setName(req.getSubWorkflowParam().getName());
            swp.setVersion(req.getSubWorkflowParam().getVersion());
            workflowTask.setSubWorkflowParam(swp);
        }
        WorkflowDef def = workflow.getWorkflowDefinition();
        List<WorkflowTask> defTasks = new ArrayList<>(def.getTasks());
        defTasks.add(workflowTask);
        def.setTasks(defTasks);
        executionDAO.updateWorkflow(workflow);

        return new InjectTaskResponse(task.getTaskId());
    }

    public CreateTrackingWorkflowResponse createTrackingWorkflow(CreateTrackingWorkflowRequest req) {
        WorkflowDef def = new WorkflowDef();
        def.setName(req.getWorkflowName());
        def.setVersion(1);
        def.setTasks(new ArrayList<>());
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
