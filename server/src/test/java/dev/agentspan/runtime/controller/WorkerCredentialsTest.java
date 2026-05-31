/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;

import dev.agentspan.runtime.auth.*;
import dev.agentspan.runtime.credentials.*;
import dev.agentspan.runtime.model.credentials.ResolveRequest;

@ExtendWith(MockitoExtension.class)
class WorkerCredentialsTest {

    @Mock
    private CredentialStoreProvider storeProvider;

    @Mock
    private CredentialResolutionService resolutionService;

    @Mock
    private ExecutionTokenService tokenService;

    @InjectMocks
    private WorkerController controller;

    @BeforeEach
    void setUp() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        tokenService = new ExecutionTokenService(key);
        ReflectionTestUtils.setField(controller, "tokenService", tokenService);
        ReflectionTestUtils.setField(controller, "resolveRateLimit", 3); // low limit for test

        RequestContextHolder.set(RequestContext.builder()
                .requestId("r1")
                .user(new User("u-test", "Test", null, "test"))
                .createdAt(Instant.now())
                .build());
    }

    @AfterEach
    void tearDown() {
        RequestContextHolder.clear();
    }

    @Test
    @SuppressWarnings("unchecked")
    void resolve_validToken_returnsValues() {
        String token = tokenService.mint("u-test", "wf-1", List.of("GITHUB_TOKEN"), 3600);
        when(resolutionService.resolve("u-test", "GITHUB_TOKEN")).thenReturn("ghp_secret");

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("GITHUB_TOKEN"));

        ResponseEntity<?> response = controller.resolveCredentials(req);
        assertThat(response.getStatusCode().value()).isEqualTo(200);

        // Response body should be a flat map, not wrapped in {"credentials": ...}
        Map<String, String> body = (Map<String, String>) response.getBody();
        assertThat(body).isNotNull();
        assertThat(body).containsEntry("GITHUB_TOKEN", "ghp_secret");
        assertThat(body).doesNotContainKey("credentials");
    }

    @Test
    void resolve_loginToken_returns401() {
        // Login tokens use wid="login" — must not be accepted at /resolve
        String loginToken = tokenService.mint("u-test", "login", List.of(), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(loginToken);
        req.setNames(List.of("GITHUB_TOKEN"));

        ResponseEntity<?> response = controller.resolveCredentials(req);
        assertThat(response.getStatusCode().value()).isEqualTo(401);
    }

    @Test
    void resolve_nameNotInDeclared_isExcluded() {
        // Token only declares GITHUB_TOKEN, but request asks for OPENAI_KEY too
        String token = tokenService.mint("u-test", "wf-1", List.of("GITHUB_TOKEN"), 3600);
        when(resolutionService.resolve(eq("u-test"), eq("GITHUB_TOKEN"))).thenReturn("ghp_val");

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("GITHUB_TOKEN", "OPENAI_KEY"));

        controller.resolveCredentials(req);

        // OPENAI_KEY must not be resolved (not in declared_names)
    }

    @Test
    void resolve_dottedPathOfDeclaredBase_isAllowed() {
        // Tool declared the parent name "GCP_SVC". A request for "GCP_SVC.project_id"
        // is allowed because the JSONPath access doesn't expand the blast radius —
        // the tool already had the whole blob via the declared parent name.
        String token = tokenService.mint("u-test", "wf-jp", List.of("GCP_SVC"), 3600);
        when(resolutionService.resolve("u-test", "GCP_SVC.project_id")).thenReturn("my-proj-123");

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("GCP_SVC.project_id"));

        @SuppressWarnings("unchecked")
        Map<String, String> body =
                (Map<String, String>) controller.resolveCredentials(req).getBody();
        assertThat(body).containsEntry("GCP_SVC.project_id", "my-proj-123");
    }

    @Test
    void resolve_dottedPathOfUndeclaredBase_isRejected() {
        // Tool declared only GITHUB_TOKEN. A request for OTHER.field must be filtered out.
        String token = tokenService.mint("u-test", "wf-jp2", List.of("GITHUB_TOKEN"), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("OTHER.field"));

        controller.resolveCredentials(req);
    }

    @Test
    void resolve_prefixCollisionGuard() {
        // Declared "FOO" must NOT permit "FOOBAR.x" — the boundary requires a dot
        // immediately after the declared name, not just a string prefix match.
        String token = tokenService.mint("u-test", "wf-jp3", List.of("FOO"), 3600);

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("FOOBAR.x"));

        controller.resolveCredentials(req);
    }

    @Test
    void resolve_rateLimitExceeded_returns429() {
        String token = tokenService.mint("u-test", "wf-2", List.of("KEY_A"), 3600);
        when(resolutionService.resolve(anyString(), anyString())).thenReturn("val");

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("KEY_A"));

        // Exhaust rate limit (3 calls allowed in test setup)
        controller.resolveCredentials(req);
        controller.resolveCredentials(req);
        controller.resolveCredentials(req);

        // 4th call should be rate-limited
        ResponseEntity<?> limited = controller.resolveCredentials(req);
        assertThat(limited.getStatusCode().value()).isEqualTo(429);
    }

    @Test
    void resolve_revokedToken_returns401() {
        String token = tokenService.mint("u-test", "wf-3", List.of("KEY_B"), 3600);
        ExecutionTokenService.TokenPayload payload = tokenService.validate(token);
        tokenService.revoke(payload.jti(), payload.exp());

        ResolveRequest req = new ResolveRequest();
        req.setToken(token);
        req.setNames(List.of("KEY_B"));

        ResponseEntity<?> response = controller.resolveCredentials(req);
        assertThat(response.getStatusCode().value()).isEqualTo(401);
    }
}
