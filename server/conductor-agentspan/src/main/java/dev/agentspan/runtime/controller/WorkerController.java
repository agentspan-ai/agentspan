/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.*;

import dev.agentspan.runtime.credentials.CredentialResolutionService;
import dev.agentspan.runtime.credentials.ExecutionTokenService;
import dev.agentspan.runtime.model.credentials.ResolveRequest;

import lombok.RequiredArgsConstructor;

/**
 * Token-mediated endpoints for distributed workers.
 *
 * <p><strong>Auth boundary:</strong> every endpoint under {@code /api/workers/*}
 * authenticates with an <strong>execution token</strong> (HMAC-SHA256, short-TTL,
 * declared-name-bound, rate-limited) — NOT a login JWT or API key.</p>
 *
 * <p>This is the AgentSpan-specific complement to {@code SecretController}:
 * Conductor has no equivalent because Conductor substitutes credential plaintext
 * into task input at dispatch time. AgentSpan workers are out-of-process and
 * pull secrets at runtime using the execution token embedded in
 * {@code __agentspan_ctx__} on the workflow.</p>
 *
 * <ul>
 *   <li>{@code POST /api/workers/secrets} — resolve declared secrets for the current execution</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/workers")
@RequiredArgsConstructor
public class WorkerController {

    private static final Logger log = LoggerFactory.getLogger(WorkerController.class);

    private final CredentialResolutionService resolutionService;
    private final ExecutionTokenService tokenService;

    /** Per-token fixed-window rate limiter (jti+minute → count). */
    private final ConcurrentHashMap<String, RateLimitBucket> rateLimitMap = new ConcurrentHashMap<>();

    @Value("${agentspan.credentials.resolve.rate-limit:120}")
    private int resolveRateLimit;

    /**
     * POST /api/workers/secrets — resolve declared secrets using an execution token.
     *
     * <p>The token is validated, rate-limited, and credential names are bounded to those
     * declared at dispatch time. Returns a map of name → plaintext for each name that
     * (a) is in the request, (b) was declared by the dispatching tool/agent, and
     * (c) exists in the store. Missing names are simply omitted from the response.</p>
     */
    @PostMapping("/secrets")
    public ResponseEntity<Map<String, String>> resolveCredentials(@RequestBody ResolveRequest request) {
        if (request.getToken() == null || request.getToken().isBlank()) {
            return ResponseEntity.status(401).body(Map.of("error", "Missing execution token"));
        }
        if (request.getNames() == null || request.getNames().isEmpty()) {
            return ResponseEntity.ok(Map.of());
        }

        ExecutionTokenService.TokenPayload payload;
        try {
            payload = tokenService.validate(request.getToken());
        } catch (ExecutionTokenService.TokenExpiredException e) {
            return ResponseEntity.status(401).body(Map.of("error", "Token expired"));
        } catch (ExecutionTokenService.TokenRevokedException e) {
            return ResponseEntity.status(401).body(Map.of("error", "Token revoked"));
        } catch (ExecutionTokenService.TokenInvalidException e) {
            return ResponseEntity.status(401).body(Map.of("error", "Token invalid"));
        }

        // Login tokens use wid="login" — reject them here, this endpoint is for
        // execution tokens only.
        if ("login".equals(payload.executionId())) {
            return ResponseEntity.status(401)
                    .body(Map.of("error", "Execution token required — login tokens are not accepted"));
        }

        if (!checkRateLimit(payload.jti())) {
            return ResponseEntity.status(429).body(Map.of("error", "Rate limit exceeded"));
        }

        // Bound requested names to those declared at dispatch time.
        // Prefix-permissive: a request for "GCP_SVC.project_id" is allowed when
        // "GCP_SVC" was declared. The JSONPath access doesn't expand the blast
        // radius — the tool already had the whole blob via the declared parent.
        // The dot boundary is required ("FOO" does NOT permit "FOOBAR.x").
        //
        // CRITICAL: an empty declared_names list means NOTHING is resolvable.
        // Earlier this branch returned the full requested list — that broke
        // the defense-in-depth claim of declared-name binding for any agent
        // that didn't declare credentials (i.e. most agents).
        List<String> declared = payload.declaredNames();
        List<String> requested = request.getNames();
        List<String> bounded = declared.isEmpty()
                ? List.of()
                : requested.stream()
                        .filter(n -> declared.contains(n) || declared.stream().anyMatch(d -> n.startsWith(d + ".")))
                        .toList();

        Map<String, String> result = new LinkedHashMap<>();
        for (String name : bounded) {
            try {
                String value = resolutionService.resolve(payload.userId(), name);
                if (value != null) result.put(name, value);
            } catch (CredentialResolutionService.CredentialNotFoundException e) {
                log.warn("Credential not found: user={}, name={}", payload.userId(), name);
            }
        }

        log.info(
                "AUDIT resolve: userId={} executionId={} names={} resolved={}",
                payload.userId(),
                payload.executionId(),
                requested,
                result.keySet());

        return ResponseEntity.ok(result);
    }

    private boolean checkRateLimit(String jti) {
        long windowStart = System.currentTimeMillis() / 60_000;
        RateLimitBucket bucket = rateLimitMap.computeIfAbsent(jti + ":" + windowStart, k -> new RateLimitBucket());
        return bucket.increment() <= resolveRateLimit;
    }

    @Scheduled(fixedDelay = 120_000)
    void pruneRateLimitWindows() {
        long cutoff = System.currentTimeMillis() / 60_000 - 2;
        rateLimitMap.keySet().removeIf(key -> {
            String[] parts = key.split(":");
            return parts.length == 2 && Long.parseLong(parts[1]) < cutoff;
        });
    }

    private static class RateLimitBucket {
        private final AtomicInteger count = new AtomicInteger(0);

        int increment() {
            return count.incrementAndGet();
        }
    }
}
