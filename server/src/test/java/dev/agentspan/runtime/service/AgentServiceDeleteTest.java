/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import com.netflix.conductor.common.metadata.tasks.Task;
import com.netflix.conductor.common.run.Workflow;
import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.dao.ExecutionDAO;
import com.netflix.conductor.dao.MetadataDAO;
import com.netflix.conductor.service.ExecutionService;
import com.netflix.conductor.service.WorkflowService;

import dev.agentspan.runtime.compiler.AgentCompiler;
import dev.agentspan.runtime.normalizer.NormalizerRegistry;
import dev.agentspan.runtime.util.ProviderValidator;

@ExtendWith(MockitoExtension.class)
class AgentServiceDeleteTest {

    @Mock
    private AgentCompiler agentCompiler;

    @Mock
    private NormalizerRegistry normalizerRegistry;

    @Mock
    private ExecutionDAO executionDAO;

    @Mock
    private MetadataDAO metadataDAO;

    @Mock
    private WorkflowExecutor workflowExecutor;

    @Mock
    private WorkflowService workflowService;

    @Mock
    private AgentStreamRegistry streamRegistry;

    @Mock
    private ExecutionService executionService;

    @Mock
    private ProviderValidator providerValidator;

    private AgentService agentService;

    @BeforeEach
    void setUp() {
        agentService = new AgentService(
                agentCompiler,
                normalizerRegistry,
                executionDAO,
                metadataDAO,
                workflowExecutor,
                workflowService,
                streamRegistry,
                executionService,
                providerValidator,
                null);
    }

    // ── deleteExecutionCascade ───────────────────────────────────────────────

    @Test
    void deleteExecutionCascade_deletesRootWorkflow_whenNoParentNoChildren() {
        Workflow wf = makeWorkflow("wf-1", null, List.of());
        when(executionService.getExecutionStatus(eq("wf-1"), anyBoolean())).thenReturn(wf);

        agentService.deleteExecutionCascade("wf-1");

        verify(workflowService).deleteWorkflow("wf-1", false);
        verifyNoMoreInteractions(workflowService);
    }

    @Test
    void deleteExecutionCascade_deletesSubWorkflows_whenParentHasChildren() {
        // Parent has two sub-workflow tasks
        Task subTask1 = makeSubWorkflowTask("sub-1");
        Task subTask2 = makeSubWorkflowTask("sub-2");
        Workflow parent = makeWorkflow("parent-1", null, List.of(subTask1, subTask2));

        // Sub-workflows have no further children
        Workflow sub1 = makeWorkflow("sub-1", "parent-1", List.of());
        Workflow sub2 = makeWorkflow("sub-2", "parent-1", List.of());

        when(executionService.getExecutionStatus(eq("parent-1"), anyBoolean())).thenReturn(parent);
        when(executionService.getExecutionStatus(eq("sub-1"), anyBoolean())).thenReturn(sub1);
        when(executionService.getExecutionStatus(eq("sub-2"), anyBoolean())).thenReturn(sub2);

        agentService.deleteExecutionCascade("parent-1");

        @SuppressWarnings("unchecked")
        ArgumentCaptor<String> idCaptor = ArgumentCaptor.forClass(String.class);
        verify(workflowService, times(3)).deleteWorkflow(idCaptor.capture(), eq(false));
        assertThat(idCaptor.getAllValues()).containsExactlyInAnyOrder("parent-1", "sub-1", "sub-2");
    }

    @Test
    void deleteExecutionCascade_resolvesParent_whenSubWorkflowIdGiven() {
        // sub-1 has parent-1 as parent
        Workflow sub1 = makeWorkflow("sub-1", "parent-1", List.of());
        // parent-1 has sub-1 as child
        Task subTask = makeSubWorkflowTask("sub-1");
        Workflow parent = makeWorkflow("parent-1", null, List.of(subTask));

        when(executionService.getExecutionStatus(eq("sub-1"), anyBoolean())).thenReturn(sub1);
        when(executionService.getExecutionStatus(eq("parent-1"), anyBoolean())).thenReturn(parent);

        agentService.deleteExecutionCascade("sub-1");

        @SuppressWarnings("unchecked")
        ArgumentCaptor<String> idCaptor = ArgumentCaptor.forClass(String.class);
        verify(workflowService, times(2)).deleteWorkflow(idCaptor.capture(), eq(false));
        assertThat(idCaptor.getAllValues()).containsExactlyInAnyOrder("parent-1", "sub-1");
    }

    // ── bulkDeleteExecutions ─────────────────────────────────────────────────

    @Test
    void bulkDeleteExecutions_deletesAllIds() {
        Workflow wf1 = makeWorkflow("wf-1", null, List.of());
        Workflow wf2 = makeWorkflow("wf-2", null, List.of());

        when(executionService.getExecutionStatus(eq("wf-1"), anyBoolean())).thenReturn(wf1);
        when(executionService.getExecutionStatus(eq("wf-2"), anyBoolean())).thenReturn(wf2);

        agentService.bulkDeleteExecutions(List.of("wf-1", "wf-2"));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<String> idCaptor = ArgumentCaptor.forClass(String.class);
        verify(workflowService, times(2)).deleteWorkflow(idCaptor.capture(), eq(false));
        assertThat(idCaptor.getAllValues()).containsExactlyInAnyOrder("wf-1", "wf-2");
    }

    @Test
    void bulkDeleteExecutions_deduplicatesRelatedIds() {
        // wf-1 has sub-1 as child; if both wf-1 and sub-1 are passed, sub-1 should only be deleted once
        Task subTask = makeSubWorkflowTask("sub-1");
        Workflow parent = makeWorkflow("wf-1", null, List.of(subTask));
        Workflow sub1 = makeWorkflow("sub-1", "wf-1", List.of());

        when(executionService.getExecutionStatus(eq("wf-1"), anyBoolean())).thenReturn(parent);
        when(executionService.getExecutionStatus(eq("sub-1"), anyBoolean())).thenReturn(sub1);

        agentService.bulkDeleteExecutions(List.of("wf-1", "sub-1"));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<String> idCaptor = ArgumentCaptor.forClass(String.class);
        verify(workflowService, times(2)).deleteWorkflow(idCaptor.capture(), eq(false));
        assertThat(idCaptor.getAllValues()).containsExactlyInAnyOrder("wf-1", "sub-1");
    }

    @Test
    void bulkDeleteExecutions_emptyList_doesNothing() {
        agentService.bulkDeleteExecutions(List.of());
        verifyNoInteractions(workflowService);
    }

    @Test
    void bulkDeleteExecutions_continuesOnPartialFailure() {
        Workflow wf1 = makeWorkflow("wf-1", null, List.of());
        Workflow wf2 = makeWorkflow("wf-2", null, List.of());

        when(executionService.getExecutionStatus(eq("wf-1"), anyBoolean())).thenReturn(wf1);
        when(executionService.getExecutionStatus(eq("wf-2"), anyBoolean())).thenReturn(wf2);

        // First delete throws, second should still proceed
        doThrow(new RuntimeException("DB error")).when(workflowService).deleteWorkflow(eq("wf-1"), eq(false));

        agentService.bulkDeleteExecutions(List.of("wf-1", "wf-2"));

        verify(workflowService).deleteWorkflow("wf-1", false);
        verify(workflowService).deleteWorkflow("wf-2", false);
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    private Workflow makeWorkflow(String id, String parentId, List<Task> tasks) {
        Workflow wf = new Workflow();
        wf.setWorkflowId(id);
        wf.setParentWorkflowId(parentId);
        wf.setTasks(new ArrayList<>(tasks));
        return wf;
    }

    private Task makeSubWorkflowTask(String subWorkflowId) {
        Task task = new Task();
        task.setSubWorkflowId(subWorkflowId);
        task.setTaskType("SUB_WORKFLOW");
        task.setStatus(Task.Status.COMPLETED);
        return task;
    }
}
