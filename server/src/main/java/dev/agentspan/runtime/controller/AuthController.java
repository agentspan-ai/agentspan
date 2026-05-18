/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import dev.agentspan.runtime.auth.User;
import dev.agentspan.runtime.auth.UserRepository;
import dev.agentspan.runtime.credentials.ExecutionTokenService;

/**
 * Auth endpoints for login (username/password → JWT).
 *
 * POST /api/auth/login  { username, password } → { token, user }
 *
 * The returned token is a HMAC-SHA256 signed JWT with scope="login".
 * It is accepted by AuthFilter as a Bearer token for subsequent requests.
 */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final UserRepository userRepository;
    private final ExecutionTokenService tokenService;

    public AuthController(UserRepository userRepository, ExecutionTokenService tokenService) {
        this.userRepository = userRepository;
        this.tokenService = tokenService;
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody Map<String, String> body) {
        String username = body.get("username");
        String password = body.get("password");
        if (username == null || username.isBlank() || password == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "username and password are required"));
        }

        if (!userRepository.checkPassword(username, password)) {
            return ResponseEntity.status(401).body(Map.of("error", "Invalid credentials"));
        }

        Optional<User> userOpt = userRepository.findByUsername(username);
        if (userOpt.isEmpty()) {
            return ResponseEntity.status(401).body(Map.of("error", "User not found"));
        }
        User user = userOpt.get();

        // Mint a login token: 24h TTL, reuse ExecutionTokenService mint
        // with userId=username (sub claim), wid="login", no declared_names
        String token = tokenService.mint(user.getUsername(), "login", List.of(), 86400);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("token", token);
        response.put(
                "user",
                Map.of(
                        "id", user.getId(),
                        "username", user.getUsername(),
                        "name", user.getName() != null ? user.getName() : user.getUsername()));
        return ResponseEntity.ok(response);
    }
}
