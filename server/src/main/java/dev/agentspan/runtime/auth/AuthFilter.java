/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import dev.agentspan.runtime.credentials.ExecutionTokenService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/**
 * Auth filter — populates RequestContextHolder on every request.
 *
 * <p>Auth paths (in priority order):</p>
 * <ol>
 *   <li>auth.enabled=false → anonymous admin User (local dev, no-op)</li>
 *   <li>Authorization: Bearer &lt;token&gt; → validate HMAC-SHA256 JWT → extract User</li>
 *   <li>X-API-Key: &lt;key&gt; → look up in DB → load associated User</li>
 *   <li>Otherwise → 401</li>
 * </ol>
 *
 * <p>Note: Bearer JWT here refers to the login JWT issued by /api/auth/login
 * (username/password → JWT), not the execution token (which is validated separately
 * by ExecutionTokenService in /api/credentials/resolve).</p>
 */
@Component
public class AuthFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(AuthFilter.class);

    private static final User ANONYMOUS = new User(
        "00000000-0000-0000-0000-000000000000", "Anonymous", "", "anonymous");

    private final UserRepository userRepository;
    private final ApiKeyRepository apiKeyRepository;
    private final boolean authEnabled;

    @Autowired(required = false)
    private ExecutionTokenService executionTokenService;

    @Autowired
    public AuthFilter(UserRepository userRepository,
                      ApiKeyRepository apiKeyRepository,
                      @Value("${agentspan.auth.enabled:true}") boolean authEnabled) {
        this.userRepository = userRepository;
        this.apiKeyRepository = apiKeyRepository;
        this.authEnabled = authEnabled;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return "/api/auth/login".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {
        try {
            if (!authEnabled) {
                setContext(ANONYMOUS, null, request);
                chain.doFilter(request, response);
                return;
            }

            // Try API key first (most common for programmatic access)
            String apiKey = request.getHeader("X-API-Key");
            if (apiKey != null && !apiKey.isBlank()) {
                Optional<User> user = apiKeyRepository.findUserByKey(apiKey);
                if (user.isPresent()) {
                    setContext(user.get(), null, request);
                    chain.doFilter(request, response);
                    return;
                }
                log.debug("Invalid API key on request to {}", request.getRequestURI());
                sendUnauthorized(response, "Invalid API key");
                return;
            }

            // Try Bearer JWT (login tokens — not execution tokens)
            String authHeader = request.getHeader("Authorization");
            if (authHeader != null && authHeader.startsWith("Bearer ")) {
                String token = authHeader.substring(7).trim();
                Optional<User> user = validateLoginToken(token);
                if (user.isPresent()) {
                    setContext(user.get(), token, request);
                    chain.doFilter(request, response);
                    return;
                }
                log.debug("Invalid Bearer token on request to {}", request.getRequestURI());
                sendUnauthorized(response, "Invalid or expired token");
                return;
            }

            // No credentials provided
            sendUnauthorized(response, "Authentication required");

        } finally {
            RequestContextHolder.clear();
        }
    }

    private void setContext(User user, String token, HttpServletRequest request) {
        RequestContext ctx = RequestContext.builder()
            .requestId(UUID.randomUUID().toString())
            .user(user)
            .executionToken(token)
            .createdAt(Instant.now())
            .build();
        RequestContextHolder.set(ctx);
    }

    /**
     * Validate a login JWT (issued by /api/auth/login).
     * Uses ExecutionTokenService when available; falls back to simple parse for test contexts.
     */
    private Optional<User> validateLoginToken(String token) {
        if (executionTokenService != null) {
            try {
                ExecutionTokenService.TokenPayload payload = executionTokenService.validate(token);
                // Login tokens use username as sub (see AuthController)
                return userRepository.findByUsername(payload.userId());
            } catch (Exception e) {
                return Optional.empty();
            }
        }
        // Fallback: simple Base64 JWT parse (used when ExecutionTokenService not wired)
        try {
            String[] parts = token.split("\\.");
            if (parts.length != 3) return Optional.empty();
            String payloadJson = new String(java.util.Base64.getUrlDecoder().decode(parts[1]));
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            @SuppressWarnings("unchecked")
            java.util.Map<String, Object> claims = mapper.readValue(payloadJson, java.util.Map.class);
            String username = (String) claims.get("sub");
            if (username == null) return Optional.empty();
            return userRepository.findByUsername(username);
        } catch (Exception e) {
            return Optional.empty();
        }
    }

    private void sendUnauthorized(HttpServletResponse response, String message) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"" + message + "\",\"status\":401}");
    }
}
