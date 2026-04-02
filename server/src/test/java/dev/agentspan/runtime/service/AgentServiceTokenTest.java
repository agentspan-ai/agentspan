/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import dev.agentspan.runtime.auth.*;
import dev.agentspan.runtime.credentials.ExecutionTokenService;

@ExtendWith(MockitoExtension.class)
class AgentServiceTokenTest {

    @Mock
    private com.netflix.conductor.core.execution.WorkflowExecutor workflowExecutor;

    @Mock
    private dev.agentspan.runtime.compiler.AgentCompiler agentCompiler;

    @Mock
    private com.netflix.conductor.dao.MetadataDAO metadataDAO;

    @Mock
    private com.netflix.conductor.service.WorkflowService workflowService;

    @Mock
    private com.netflix.conductor.service.ExecutionService executionService;

    @Mock
    private dev.agentspan.runtime.service.AgentStreamRegistry streamRegistry;

    @Mock
    private dev.agentspan.runtime.normalizer.NormalizerRegistry normalizerRegistry;

    @Mock
    private dev.agentspan.runtime.util.ProviderValidator providerValidator;

    private AgentService agentService;
    private ExecutionTokenService tokenService;

    @BeforeEach
    void setUp() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        tokenService = new ExecutionTokenService(key);

        agentService = new AgentService(
                agentCompiler,
                normalizerRegistry,
                metadataDAO,
                workflowExecutor,
                workflowService,
                streamRegistry,
                executionService,
                providerValidator,
                tokenService);

        RequestContextHolder.set(RequestContext.builder()
                .requestId("r1")
                .user(new User("user-999", "Test", null, "tester"))
                .createdAt(Instant.now())
                .build());
    }

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    void start_injectsExecutionToken_intoWorkflowInput() {
        com.netflix.conductor.common.metadata.workflow.WorkflowDef def =
                new com.netflix.conductor.common.metadata.workflow.WorkflowDef();
        def.setName("test_agent");
        def.setVersion(1);
        when(agentCompiler.compile(any())).thenReturn(def);
        when(workflowExecutor.startWorkflow(any())).thenReturn("wf-xyz");
        when(providerValidator.validateProvider(any())).thenReturn(java.util.Optional.empty());

        dev.agentspan.runtime.model.StartRequest req = dev.agentspan.runtime.model.StartRequest.builder()
                .agentConfig(dev.agentspan.runtime.model.AgentConfig.builder()
                        .name("test_agent")
                        .model("openai/gpt-4o")
                        .credentials(new ArrayList<>(List.of("AGENT_LEVEL")))
                        .build())
                .prompt("hello")
                .credentials(List.of("REQUEST_LEVEL"))
                .build();

        agentService.start(req);

        ArgumentCaptor<com.netflix.conductor.core.execution.StartWorkflowInput> captor =
                ArgumentCaptor.forClass(com.netflix.conductor.core.execution.StartWorkflowInput.class);
        verify(workflowExecutor).startWorkflow(captor.capture());

        java.util.Map<String, Object> input = captor.getValue().getWorkflowInput();
        assertThat(input).containsKey("__agentspan_ctx__");

        @SuppressWarnings("unchecked")
        java.util.Map<String, Object> ctx = (java.util.Map<String, Object>) input.get("__agentspan_ctx__");
        assertThat(ctx).containsKey("execution_token");

        String executionToken = (String) ctx.get("execution_token");
        ExecutionTokenService.TokenPayload payload = tokenService.validate(executionToken);
        assertThat(payload.userId()).isEqualTo("user-999");
        assertThat(payload.declaredNames()).containsExactlyInAnyOrder("AGENT_LEVEL", "REQUEST_LEVEL");
        assertThat(input.get("credentials")).isEqualTo(List.of("REQUEST_LEVEL"));
    }

    @Test
    void start_withoutRequestCredentials_omitsCredentialsInput() {
        com.netflix.conductor.common.metadata.workflow.WorkflowDef def =
                new com.netflix.conductor.common.metadata.workflow.WorkflowDef();
        def.setName("test_agent");
        def.setVersion(1);
        when(agentCompiler.compile(any())).thenReturn(def);
        when(workflowExecutor.startWorkflow(any())).thenReturn("wf-xyz");
        when(providerValidator.validateProvider(any())).thenReturn(java.util.Optional.empty());

        dev.agentspan.runtime.model.StartRequest req = dev.agentspan.runtime.model.StartRequest.builder()
                .agentConfig(dev.agentspan.runtime.model.AgentConfig.builder()
                        .name("test_agent")
                        .model("openai/gpt-4o")
                        .build())
                .prompt("hello")
                .build();

        agentService.start(req);

        ArgumentCaptor<com.netflix.conductor.core.execution.StartWorkflowInput> captor =
                ArgumentCaptor.forClass(com.netflix.conductor.core.execution.StartWorkflowInput.class);
        verify(workflowExecutor).startWorkflow(captor.capture());

        Map<String, Object> input = captor.getValue().getWorkflowInput();
        assertThat(input).doesNotContainKey("credentials");
    }

    @Test
    void start_rejectsBlankInputWithoutMediaOrContext() {
        dev.agentspan.runtime.model.StartRequest req = dev.agentspan.runtime.model.StartRequest.builder()
                .agentConfig(dev.agentspan.runtime.model.AgentConfig.builder()
                        .name("test_agent")
                        .model("openai/gpt-4o")
                        .build())
                .prompt("   ")
                .build();

        assertThatThrownBy(() -> agentService.start(req))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("non-empty prompt");

        verifyNoInteractions(agentCompiler, workflowExecutor);
    }

    @Test
    void start_includesContextInWorkflowInput() {
        com.netflix.conductor.common.metadata.workflow.WorkflowDef def =
                new com.netflix.conductor.common.metadata.workflow.WorkflowDef();
        def.setName("test_agent");
        def.setVersion(1);
        when(agentCompiler.compile(any())).thenReturn(def);
        when(workflowExecutor.startWorkflow(any())).thenReturn("wf-xyz");
        when(providerValidator.validateProvider(any())).thenReturn(java.util.Optional.empty());

        dev.agentspan.runtime.model.StartRequest req = dev.agentspan.runtime.model.StartRequest.builder()
                .agentConfig(dev.agentspan.runtime.model.AgentConfig.builder()
                        .name("test_agent")
                        .model("openai/gpt-4o")
                        .build())
                .prompt("hello")
                .context(Map.of("repo", "acme"))
                .build();

        agentService.start(req);

        ArgumentCaptor<com.netflix.conductor.core.execution.StartWorkflowInput> captor =
                ArgumentCaptor.forClass(com.netflix.conductor.core.execution.StartWorkflowInput.class);
        verify(workflowExecutor).startWorkflow(captor.capture());

        Map<String, Object> input = captor.getValue().getWorkflowInput();
        assertThat(input.get("context")).isEqualTo(Map.of("repo", "acme"));
    }
}
