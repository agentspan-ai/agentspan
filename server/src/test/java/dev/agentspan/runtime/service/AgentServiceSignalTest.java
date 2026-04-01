/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

import java.util.NoSuchElementException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import com.netflix.conductor.core.execution.WorkflowExecutor;
import com.netflix.conductor.model.WorkflowModel;

import dev.agentspan.runtime.model.SignalReceipt;
import dev.agentspan.runtime.model.SignalRequest;

/**
 * Unit tests for AgentService.signal().
 * Stubs — full implementation tested in AgentControllerSignalTest (E2E).
 * TODO: complete in Task 3+ once AgentService.signal() is implemented.
 */
@ExtendWith(MockitoExtension.class)
class AgentServiceSignalTest {

    @Mock
    private WorkflowExecutor workflowExecutor;

    @Mock
    private dev.agentspan.runtime.compiler.AgentCompiler agentCompiler;

    @Mock
    private com.netflix.conductor.dao.MetadataDAO metadataDAO;

    @Mock
    private com.netflix.conductor.service.WorkflowService workflowService;

    @Mock
    private com.netflix.conductor.service.ExecutionService executionService;

    @Mock
    private AgentStreamRegistry streamRegistry;

    @Mock
    private dev.agentspan.runtime.normalizer.NormalizerRegistry normalizerRegistry;

    @Mock
    private dev.agentspan.runtime.util.ProviderValidator providerValidator;

    private AgentService agentService;

    @BeforeEach
    void setUp() {
        agentService = new AgentService(
                agentCompiler, normalizerRegistry, metadataDAO,
                workflowExecutor, workflowService, streamRegistry,
                executionService, providerValidator, null);
    }

    /**
     * signal() must throw NoSuchElementException when the workflow is not found.
     * TODO: enable once AgentService.signal() is implemented.
     */
    @Test
    @Disabled("TODO: implement AgentService.signal() in Task 3")
    void signal_workflowNotFound_throwsNoSuchElementException() {
        when(workflowExecutor.getWorkflow(eq("missing-id"), eq(false))).thenReturn(null);

        SignalRequest req = new SignalRequest();
        req.setMessage("hello");

        assertThatThrownBy(() -> agentService.signal("missing-id", req))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessageContaining("missing-id");
    }

    /**
     * signal() must throw IllegalArgumentException when message exceeds 4096 characters.
     * TODO: enable once AgentService.signal() is implemented.
     */
    @Test
    @Disabled("TODO: implement AgentService.signal() in Task 3")
    void signal_messageTooLong_throwsIllegalArgumentException() {
        SignalRequest req = new SignalRequest();
        req.setMessage("x".repeat(4097));

        assertThatThrownBy(() -> agentService.signal("some-id", req))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("4096");
    }

    /**
     * signal() on a RUNNING workflow must return a SignalReceipt with status "queued".
     * TODO: enable once AgentService.signal() is implemented.
     */
    @Test
    @Disabled("TODO: implement AgentService.signal() in Task 3")
    void signal_runningWorkflow_returnsQueuedReceipt() {
        WorkflowModel wf = new WorkflowModel();
        wf.setWorkflowId("run-id-1");
        wf.setStatus(WorkflowModel.Status.RUNNING);
        when(workflowExecutor.getWorkflow(eq("run-id-1"), eq(false))).thenReturn(wf);
        when(workflowExecutor.getWorkflow(eq("run-id-1"), eq(false))).thenReturn(wf);

        SignalRequest req = new SignalRequest();
        req.setMessage("do something");
        req.setPriority("normal");

        SignalReceipt receipt = agentService.signal("run-id-1", req);

        assertThat(receipt).isNotNull();
        assertThat(receipt.getStatus()).isEqualTo("queued");
        assertThat(receipt.getExecutionId()).isEqualTo("run-id-1");
        assertThat(receipt.getSignalId()).isNotBlank();
    }
}
