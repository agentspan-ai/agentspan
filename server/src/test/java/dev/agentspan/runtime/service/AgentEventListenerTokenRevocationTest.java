/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.service;

import com.netflix.conductor.model.WorkflowModel;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.security.SecureRandom;
import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AgentEventListenerTokenRevocationTest {

    @Mock private AgentStreamRegistry streamRegistry;

    private ExecutionTokenService tokenService;
    private AgentEventListener listener;

    @BeforeEach
    void setUp() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        tokenService = spy(new ExecutionTokenService(key));
        listener = new AgentEventListener(streamRegistry, tokenService);
    }

    @Test
    void onWorkflowTerminated_revokesExecutionToken() {
        String token = tokenService.mint("u1", "wf-1", List.of(), 3600);
        ExecutionTokenService.TokenPayload payload = tokenService.validate(token);

        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-1");
        workflow.setStatus(WorkflowModel.Status.TERMINATED);
        workflow.setVariables(Map.of("__agentspan_ctx__",
            Map.of("execution_token", token)));

        listener.onWorkflowTerminatedIfEnabled(workflow);

        verify(tokenService).revoke(payload.jti(), payload.exp());
    }

    @Test
    void onWorkflowCompleted_revokesExecutionToken() {
        String token = tokenService.mint("u1", "wf-2", List.of(), 3600);
        ExecutionTokenService.TokenPayload payload = tokenService.validate(token);

        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-2");
        workflow.setStatus(WorkflowModel.Status.COMPLETED);
        workflow.setOutput(Map.of());
        workflow.setVariables(Map.of("__agentspan_ctx__",
            Map.of("execution_token", token)));

        listener.onWorkflowCompletedIfEnabled(workflow);

        verify(tokenService).revoke(payload.jti(), payload.exp());
    }
}
