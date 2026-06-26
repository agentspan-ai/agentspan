/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
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
 * The masking substitution contract in {@link CredentialMaskingResponseAdvice}.
 *
 * <p>OSS ships a no-op {@code SecretOutputMasker}, so a full-stack test can only show values pass
 * through unchanged. The redaction <em>algorithm</em> (disclosure lookup, Jackson tree-walk,
 * JSON-escape handling) lives in the enterprise module and is tested there. What is OSS-testable —
 * and what neither {@code CredentialMaskingIntegrationTest} (real no-op masker) nor
 * {@code CredentialMaskingWorkflowOptInTest} (echo masker, only verifies the masker is
 * <em>consulted</em>) asserts — is the <strong>pipeline contract</strong>: given a masker that
 * returns a redacted payload, the advice must put that redacted body on the wire, not the original.</p>
 *
 * <p>A stand-in masker (replacing the secret with {@code ***NAME***}) lets us prove the substitution
 * end-to-end without depending on the enterprise redaction logic.</p>
 */
class CredentialMaskingSubstitutionTest {

    private static final String USER_ID = "00000000-0000-0000-0000-000000000000";
    private static final String EXEC_ID = "exec-1";
    private static final String SECRET = "ghp_supersecretvalue";

    private final SecretOutputMasker masker = mock(SecretOutputMasker.class);
    private final ObjectMapper mapper = new ObjectMapper();
    private final CredentialMaskingResponseAdvice advice =
            new CredentialMaskingResponseAdvice(masker, mapper, false);

    @AfterEach
    void clearContext() {
        RequestContextHolder.clear();
    }

    private void setUser() {
        RequestContextHolder.set(RequestContext.builder()
                .requestId(UUID.randomUUID().toString())
                .userId(USER_ID)
                .createdAt(Instant.now())
                .build());
    }

    private Object invoke(String path, Object body) {
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        when(request.getURI()).thenReturn(URI.create("http://localhost:6767" + path));
        ServerHttpResponse response = mock(ServerHttpResponse.class);
        return advice.beforeBodyWrite(body, null, MediaType.APPLICATION_JSON, null, request, response);
    }

    @Test
    void redactedPayloadFromMasker_isWhatGoesOnTheWire() throws Exception {
        setUser();
        // Stand-in masker: replace the literal secret with ***GITHUB_TOKEN*** in the JSON.
        when(masker.mask(eq(EXEC_ID), eq(USER_ID), any()))
                .thenAnswer(inv -> ((String) inv.getArgument(2)).replace(SECRET, "***GITHUB_TOKEN***"));

        Object body = Map.of("output", "token is " + SECRET);
        Object result = invoke("/api/agent/executions/" + EXEC_ID, body);

        // The advice must return the MASKED body, not the original.
        String serialized = mapper.writeValueAsString(result);
        assertThat(serialized).doesNotContain(SECRET);
        assertThat(serialized).contains("***GITHUB_TOKEN***");
    }

    @Test
    void unchangedPayload_returnsOriginalBodyInstance_fastPath() {
        setUser();
        // Masker echoes the payload back (the OSS no-op shape): advice short-circuits.
        when(masker.mask(any(), any(), any())).thenAnswer(inv -> inv.getArgument(2));

        Object body = Map.of("output", "token is " + SECRET);
        Object result = invoke("/api/agent/executions/" + EXEC_ID, body);

        // No change → the original body instance is returned untouched (no needless re-parse).
        assertThat(result).isSameAs(body);
    }

    @Test
    void maskerThrows_bodyReturnedUnchanged_neverBlocksResponse() {
        setUser();
        // Masking is best-effort defense in depth — a failing masker must not break the response.
        when(masker.mask(any(), any(), any())).thenThrow(new RuntimeException("masker boom"));

        Object body = Map.of("output", "token is " + SECRET);
        Object result = invoke("/api/agent/executions/" + EXEC_ID, body);

        assertThat(result).isSameAs(body);
    }
}
