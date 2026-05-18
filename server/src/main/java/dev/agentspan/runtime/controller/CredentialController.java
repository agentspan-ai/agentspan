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
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.*;

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.credentials.*;
import dev.agentspan.runtime.model.credentials.*;

import lombok.RequiredArgsConstructor;

/**
 * REST controller for credential management and runtime resolution.
 *
 * <p>Management endpoints (/api/credentials/**) require a logged-in user
 * (set by AuthFilter). The /resolve endpoint requires an execution token
 * (validated by ExecutionTokenService — NOT the login JWT).</p>
 */
@RestController
@RequestMapping("/api/credentials")
@RequiredArgsConstructor
public class CredentialController {

    private static final Logger log = LoggerFactory.getLogger(CredentialController.class);

    private final CredentialStoreProvider storeProvider;
    private final CredentialBindingService bindingService;
    private final CredentialResolutionService resolutionService;
    private final ExecutionTokenService tokenService;

    // In-memory per-token rate limiter: token jti → call count in current window
    // Simple fixed-window rate limit (120 calls/min per token)
    private final ConcurrentHashMap<String, RateLimitBucket> rateLimitMap = new ConcurrentHashMap<>();

    @Value("${agentspan.credentials.resolve.rate-limit:120}")
    private int resolveRateLimit;

    // ── Credential CRUD ───────────────────────────────────────────────

    /** GET /api/credentials — list all credentials (name, partial, timestamps) */
    @GetMapping
    public ResponseEntity<?> listCredentials() {
        String userId = currentUserId();
        List<CredentialMeta> list = storeProvider.list(userId);
        return ResponseEntity.ok(list);
    }

    /** GET /api/credentials/{name} — get metadata for a single credential */
    @GetMapping("/{name}")
    public ResponseEntity<?> getCredential(@PathVariable String name) {
        log.info("Request to get {}", name);
        String userId = currentUserId();
        List<CredentialMeta> all = storeProvider.list(userId);
        log.info("Got: {}", all);
        return all.stream()
                .filter(m -> m.getName().equals(name))
                .findFirst()
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /** POST /api/credentials — create a credential { name, value } */
    @PostMapping
    public ResponseEntity<?> createCredential(@RequestBody Map<String, String> body) {
        String userId = currentUserId();
        String name = body.get("name");
        String value = body.get("value");
        if (name == null || name.isBlank() || value == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "name and value are required"));
        }
        storeProvider.set(userId, name, value);
        log.info("Credential created: user={}, name={}", userId, name);
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    /** PUT /api/credentials/{name} — update a credential value */
    @PutMapping("/{name}")
    public ResponseEntity<?> updateCredential(@PathVariable String name, @RequestBody Map<String, String> body) {
        String userId = currentUserId();
        String value = body.get("value");
        if (value == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "value is required"));
        }
        storeProvider.set(userId, name, value);
        log.info("Credential updated: user={}, name={}", userId, name);
        return ResponseEntity.ok().build();
    }

    /** DELETE /api/credentials/{name} — delete a credential */
    @DeleteMapping("/{name}")
    public ResponseEntity<?> deleteCredential(@PathVariable String name) {
        String userId = currentUserId();
        storeProvider.delete(userId, name);
        log.info("Credential deleted: user={}, name={}", userId, name);
        return ResponseEntity.noContent().build();
    }

    // ── Bindings ──────────────────────────────────────────────────────

    /** GET /api/credentials/bindings — list all bindings */
    @GetMapping("/bindings")
    public ResponseEntity<?> listBindings() {
        Map<String, String> bindings = bindingService.listBindings(currentUserId());
        List<Map<String, String>> list = bindings.entrySet().stream()
                .map(e -> Map.of("logical_key", e.getKey(), "store_name", e.getValue()))
                .collect(Collectors.toList());
        return ResponseEntity.ok(list);
    }

    /** PUT /api/credentials/bindings/{key} — set a binding { store_name } */
    @PutMapping("/bindings/{key}")
    public ResponseEntity<?> setBinding(@PathVariable String key, @RequestBody Map<String, String> body) {
        String userId = currentUserId();
        String storeName = body.get("store_name");
        if (storeName == null || storeName.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "store_name is required"));
        }
        bindingService.setBinding(userId, key, storeName);
        return ResponseEntity.ok().build();
    }

    /** DELETE /api/credentials/bindings/{key} — remove a binding */
    @DeleteMapping("/bindings/{key}")
    public ResponseEntity<?> deleteBinding(@PathVariable String key) {
        bindingService.deleteBinding(currentUserId(), key);
        return ResponseEntity.noContent().build();
    }

    // ── Runtime resolve ───────────────────────────────────────────────

    /**
     * POST /api/credentials/resolve — resolve credentials for worker use.
     *
     * <p>Requires an execution token (NOT a login JWT). The token is validated,
     * rate-limited, and credential names are bounded to those declared at compile time.</p>
     */
    @PostMapping("/resolve")
    public ResponseEntity<Map<String, String>> resolve(@RequestBody ResolveRequest request) {
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

        // Reject login tokens — only execution tokens are accepted at /resolve
        if ("login".equals(payload.executionId())) {
            return ResponseEntity.status(401)
                    .body(Map.of("error", "Execution token required for /resolve — login tokens are not accepted"));
        }

        // Rate limit check
        if (!checkRateLimit(payload.jti())) {
            return ResponseEntity.status(429).body(Map.of("error", "Rate limit exceeded"));
        }

        // Bound credential names to those declared at compile time
        List<String> declared = payload.declaredNames();
        List<String> requested = request.getNames();
        List<String> bounded = declared.isEmpty()
                ? requested
                : requested.stream().filter(declared::contains).toList();

        // Resolve each name
        Map<String, String> result = new LinkedHashMap<>();
        for (String name : bounded) {
            try {
                String value = resolutionService.resolve(payload.userId(), name);
                if (value != null) result.put(name, value);
            } catch (CredentialResolutionService.CredentialNotFoundException e) {
                log.warn("Credential not found: user={}, name={}", payload.userId(), name);
            }
        }

        // Audit log
        log.info(
                "AUDIT resolve: userId={} executionId={} names={} resolved={}",
                payload.userId(),
                payload.executionId(),
                requested,
                result.keySet());

        return ResponseEntity.ok(result);
    }

    // ── Helpers ───────────────────────────────────────────────────────

    private String currentUserId() {
        return RequestContextHolder.getRequiredUser().getId();
    }

    private boolean checkRateLimit(String jti) {
        long windowStart = System.currentTimeMillis() / 60_000;
        RateLimitBucket bucket = rateLimitMap.computeIfAbsent(jti + ":" + windowStart, k -> new RateLimitBucket());
        return bucket.increment() <= resolveRateLimit;
    }

    /** Periodically evict stale rate-limit window entries to prevent unbounded growth. */
    @Scheduled(fixedDelay = 120_000) // every 2 minutes
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
