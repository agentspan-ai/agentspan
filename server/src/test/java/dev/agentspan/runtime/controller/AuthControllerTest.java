/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import dev.agentspan.runtime.auth.UserRepository;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.ResponseEntity;

import java.security.SecureRandom;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AuthControllerTest {

    @Mock private UserRepository userRepository;

    private AuthController controller;

    @org.junit.jupiter.api.BeforeEach
    void setUp() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        ExecutionTokenService tokenService = new ExecutionTokenService(key);
        controller = new AuthController(userRepository, tokenService);
    }

    @Test
    void login_validCredentials_returnsToken() {
        when(userRepository.checkPassword("alice", "secret")).thenReturn(true);
        when(userRepository.findByUsername("alice")).thenReturn(
            java.util.Optional.of(new dev.agentspan.runtime.auth.User("u1", "Alice", null, "alice")));

        ResponseEntity<?> response = controller.login(Map.of("username", "alice", "password", "secret"));

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        @SuppressWarnings("unchecked")
        Map<String, Object> body = (Map<String, Object>) response.getBody();
        assertThat(body).containsKey("token");
        assertThat((String) body.get("token")).contains(".");
    }

    @Test
    void login_wrongPassword_returns401() {
        when(userRepository.checkPassword("alice", "wrong")).thenReturn(false);

        ResponseEntity<?> response = controller.login(Map.of("username", "alice", "password", "wrong"));

        assertThat(response.getStatusCode().value()).isEqualTo(401);
    }

    @Test
    void login_missingFields_returns400() {
        ResponseEntity<?> response = controller.login(Map.of("username", "alice"));
        assertThat(response.getStatusCode().value()).isEqualTo(400);
    }
}
