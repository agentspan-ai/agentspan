/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.context.RequestContext;
import dev.agentspan.runtime.context.RequestContextHolder;
import dev.agentspan.runtime.spi.SecretOutputMasker;

/**
 * Verifies that {@link CredentialMaskingResponseAdvice} only intercepts the host-owned
 * {@code /api/workflow/{id}} endpoint when explicitly opted in
 * ({@code agentspan.credentials.mask-workflow-reads=true}), while AgentSpan's own
 * {@code /api/agent/*} reads are always masked. This guards against the library mutating
 * an embedding host's raw Conductor responses just by being on the classpath.
 */
class CredentialMaskingWorkflowOptInTest {

    private static final String USER_ID = "00000000-0000-0000-0000-000000000000";

    private final SecretOutputMasker masker = mock(SecretOutputMasker.class);
    private final ObjectMapper mapper = new ObjectMapper();

    @AfterEach
    void clearContext() {
        RequestContextHolder.clear();
    }

    private CredentialMaskingResponseAdvice advice(boolean maskWorkflowReads) {
        // Masker echoes the payload back (no-op) so the advice's return value is the parsed body.
        when(masker.mask(any(), any(), any())).thenAnswer(inv -> inv.getArgument(2));
        return new CredentialMaskingResponseAdvice(masker, mapper, maskWorkflowReads);
    }

    private void setUser() {
        RequestContextHolder.set(RequestContext.builder()
                .requestId(UUID.randomUUID().toString())
                .userId(USER_ID)
                .createdAt(Instant.now())
                .build());
    }

    private Object invoke(CredentialMaskingResponseAdvice advice, String path, Object body) {
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        when(request.getURI()).thenReturn(URI.create("http://localhost:6767" + path));
        ServerHttpResponse response = mock(ServerHttpResponse.class);
        return advice.beforeBodyWrite(body, null, MediaType.APPLICATION_JSON, null, request, response);
    }

    @Test
    void workflowRead_notMasked_whenOptInDisabled() {
        setUser();
        Object body = Map.of("workflowId", "wf-1", "output", "secret-value");

        Object result = invoke(advice(false), "/api/workflow/wf-1", body);

        // Host endpoint must be left completely untouched — same instance, masker never consulted.
        assertThat(result).isSameAs(body);
        verify(masker, never()).mask(any(), any(), any());
    }

    @Test
    void workflowRead_masked_whenOptInEnabled() {
        setUser();
        Object body = Map.of("workflowId", "wf-1", "output", "secret-value");

        invoke(advice(true), "/api/workflow/wf-1", body);

        verify(masker).mask(eq("wf-1"), eq(USER_ID), any());
    }

    @Test
    void agentExecutionRead_alwaysMasked_evenWhenWorkflowOptInDisabled() {
        setUser();
        Object body = Map.of("executionId", "exec-1", "output", "secret-value");

        invoke(advice(false), "/api/agent/executions/exec-1", body);

        // AgentSpan owns /api/agent/* — masking there is unaffected by the workflow opt-in.
        verify(masker).mask(eq("exec-1"), eq(USER_ID), any());
    }
}
