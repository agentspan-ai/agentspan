/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.service;

import static org.mockito.Mockito.*;

import java.security.SecureRandom;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import com.netflix.conductor.model.WorkflowModel;

import dev.agentspan.runtime.credentials.HmacExecutionTokenIssuer;
import dev.agentspan.runtime.spi.ExecutionTokenIssuer;

@ExtendWith(MockitoExtension.class)
class AgentEventListenerTokenRevocationTest {

    @Mock
    private AgentStreamRegistry streamRegistry;

    private ExecutionTokenIssuer tokenIssuer;
    private AgentEventListener listener;

    @BeforeEach
    void setUp() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        tokenIssuer = spy(new HmacExecutionTokenIssuer(() -> key));
        listener = new AgentEventListener(streamRegistry, tokenIssuer);
    }

    @Test
    void onWorkflowTerminated_revokesExecutionToken() {
        String token = tokenIssuer.mint("u1", "wf-1", List.of(), 3600);
        ExecutionTokenIssuer.TokenPayload payload = tokenIssuer.validate(token);

        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-1");
        workflow.setStatus(WorkflowModel.Status.TERMINATED);
        workflow.setVariables(Map.of("__agentspan_ctx__", Map.of("execution_token", token)));

        listener.onWorkflowTerminatedIfEnabled(workflow);

        verify(tokenIssuer).revoke(payload.jti(), payload.exp());
    }

    @Test
    void onWorkflowCompleted_revokesExecutionToken() {
        String token = tokenIssuer.mint("u1", "wf-2", List.of(), 3600);
        ExecutionTokenIssuer.TokenPayload payload = tokenIssuer.validate(token);

        WorkflowModel workflow = new WorkflowModel();
        workflow.setWorkflowId("wf-2");
        workflow.setStatus(WorkflowModel.Status.COMPLETED);
        workflow.setOutput(Map.of());
        workflow.setVariables(Map.of("__agentspan_ctx__", Map.of("execution_token", token)));

        listener.onWorkflowCompletedIfEnabled(workflow);

        verify(tokenIssuer).revoke(payload.jti(), payload.exp());
    }
}
