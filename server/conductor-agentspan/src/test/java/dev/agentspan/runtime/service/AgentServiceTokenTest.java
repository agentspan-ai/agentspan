/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.time.Instant;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import dev.agentspan.runtime.context.*;

@ExtendWith(MockitoExtension.class)
class AgentServiceTokenTest {

    @Mock
    private com.netflix.conductor.core.execution.WorkflowExecutor workflowExecutor;

    @Mock
    private dev.agentspan.runtime.compiler.AgentCompiler agentCompiler;

    @Mock
    private com.netflix.conductor.dao.ExecutionDAO executionDAO;

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

    @Mock
    private SkillRegistryService skillRegistryService;

    @Mock
    private com.netflix.conductor.core.utils.IDGenerator idGenerator;

    @Mock
    private com.netflix.conductor.service.MetadataService metadataService;

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
                skillRegistryService,
                idGenerator,
                metadataService);

        RequestContextHolder.set(RequestContext.builder()
                .requestId("r1")
                .userId("user-999")
                .createdAt(Instant.now())
                .build());
    }

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
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
