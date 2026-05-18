/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.netflix.conductor.model.TaskModel;
import com.netflix.conductor.model.WorkflowModel;

import dev.agentspan.runtime.model.AgentSSEEvent;

class AgentHumanTaskTest {

    private AgentStreamRegistry streamRegistry;
    private AgentHumanTask humanTask;

    @BeforeEach
    void setUp() {
        streamRegistry = mock(AgentStreamRegistry.class);
        humanTask = new AgentHumanTask(streamRegistry);
    }

    @Test
    void startSetsInProgressAndEmitsWaiting() {
        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-1");

        TaskModel task = new TaskModel();
        task.setReferenceTaskName("hitl_approve");
        task.setInputData(Map.of("tool_name", "publish_article", "parameters", Map.of("title", "Test")));

        humanTask.start(workflow, task, null);

        assertThat(task.getStatus()).isEqualTo(TaskModel.Status.IN_PROGRESS);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-1"), captor.capture());
        AgentSSEEvent event = captor.getValue();
        assertThat(event.getType()).isEqualTo("waiting");
        assertThat(event.getPendingTool()).containsEntry("tool_name", "publish_article");
        assertThat(event.getPendingTool()).containsEntry("taskRefName", "hitl_approve");
        assertThat(event.getExecutionId()).isEqualTo("wf-1");
    }

    @Test
    void startWithNullInputData() {
        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-2");

        TaskModel task = new TaskModel();
        task.setReferenceTaskName("hitl_task");

        humanTask.start(workflow, task, null);

        assertThat(task.getStatus()).isEqualTo(TaskModel.Status.IN_PROGRESS);

        ArgumentCaptor<AgentSSEEvent> captor = ArgumentCaptor.forClass(AgentSSEEvent.class);
        verify(streamRegistry).send(eq("wf-2"), captor.capture());
        AgentSSEEvent event = captor.getValue();
        assertThat(event.getType()).isEqualTo("waiting");
        assertThat(event.getPendingTool()).containsEntry("taskRefName", "hitl_task");
    }

    @Test
    void startContinuesEvenIfSseFails() {
        doThrow(new RuntimeException("SSE send failed")).when(streamRegistry).send(anyString(), any());

        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-3");
        TaskModel task = new TaskModel();
        task.setReferenceTaskName("hitl");

        // Should not throw
        assertThatCode(() -> humanTask.start(workflow, task, null)).doesNotThrowAnyException();

        // Task should still be IN_PROGRESS even if SSE failed
        assertThat(task.getStatus()).isEqualTo(TaskModel.Status.IN_PROGRESS);
    }

    @Test
    void cancelSetsCanceled() {
        WorkflowModel workflow = new WorkflowModel();
        TaskModel task = new TaskModel();

        humanTask.cancel(workflow, task, null);

        assertThat(task.getStatus()).isEqualTo(TaskModel.Status.CANCELED);
    }
}
