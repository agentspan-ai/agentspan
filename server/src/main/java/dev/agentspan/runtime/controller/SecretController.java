/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.credentials.CredentialStoreProvider;
import dev.agentspan.runtime.model.credentials.CredentialMeta;

import lombok.RequiredArgsConstructor;

/**
 * REST controller for secrets — Conductor-parity contract.
 *
 * <p>Mirrors {@code io.orkes.conductor.server.rest.SecretResource} (v1) and
 * {@code SecretResourceV2}. Auth: every endpoint requires a logged-in
 * session (login JWT or API key, set by {@link dev.agentspan.runtime.auth.AuthFilter}).</p>
 *
 * <p>The token-mediated worker fetch endpoint lives in {@link WorkerController}
 * at {@code POST /api/workers/secrets}.</p>
 *
 * <ul>
 *   <li>{@code POST   /api/secrets}              — list names ({@code List<String>})</li>
 *   <li>{@code GET    /api/secrets}              — list names user can grant access to ({@code Set<String>})</li>
 *   <li>{@code GET    /api/secrets/v2}           — richer metadata (name, partial, timestamps)</li>
 *   <li>{@code GET    /api/secrets/{key}}        — plaintext value (text/plain)</li>
 *   <li>{@code PUT    /api/secrets/{key}}        — upsert; raw-string body (max 65535 chars)</li>
 *   <li>{@code DELETE /api/secrets/{key}}        — delete (200 OK, Conductor parity)</li>
 *   <li>{@code GET    /api/secrets/{key}/exists} — boolean</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/secrets")
@RequiredArgsConstructor
public class SecretController {

    private static final Logger log = LoggerFactory.getLogger(SecretController.class);

    /** Mirrors Conductor's {@code SecretsService.ALLOWED_SECRET_NAME_PATTERN}. */
    static final String KEY_PATTERN = "[a-zA-Z0-9_-]+";

    static final int MAX_KEY_LENGTH = 65535;
    private static final Pattern KEY_REGEX = Pattern.compile(KEY_PATTERN);

    private final CredentialStoreProvider storeProvider;

    // ── List ──────────────────────────────────────────────────────────

    /** POST /api/secrets — list all secret names (Conductor's primary listing endpoint). */
    @PostMapping
    public ResponseEntity<List<String>> listAllNames() {
        List<String> names = storeProvider.list(currentUserId()).stream()
                .map(CredentialMeta::getName)
                .toList();
        return ResponseEntity.ok(names);
    }

    /**
     * GET /api/secrets — list names the caller can grant access to.
     * Returns {@code Set<String>} (Conductor parity — deduplication, no ordering guarantee).
     * In OSS (no RBAC) this is the same set as POST.
     */
    @GetMapping
    public ResponseEntity<Set<String>> listGrantable() {
        Set<String> names = new LinkedHashSet<>(storeProvider.list(currentUserId()).stream()
                .map(CredentialMeta::getName)
                .toList());
        return ResponseEntity.ok(names);
    }

    /**
     * GET /api/secrets/v2 — list with metadata (mirrors Conductor's SecretResourceV2).
     * Returns name + partial value + timestamps. Used by the CLI and UI.
     */
    @GetMapping("/v2")
    public ResponseEntity<List<CredentialMeta>> listWithMeta() {
        return ResponseEntity.ok(storeProvider.list(currentUserId()));
    }

    // ── Value CRUD ────────────────────────────────────────────────────

    /** GET /api/secrets/{key} — plaintext value. */
    @GetMapping(value = "/{key}", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> getSecret(@PathVariable String key) {
        ResponseEntity<?> err = validateKey(key);
        if (err != null) return ResponseEntity.status(err.getStatusCode()).build();
        String value = storeProvider.get(currentUserId(), key);
        log.info("AUDIT get-secret: userId={} key={} found={}", currentUserId(), key, value != null);
        if (value == null) return ResponseEntity.notFound().build();
        return ResponseEntity.ok(value);
    }

    /** PUT /api/secrets/{key} — upsert; body is the raw secret value (max 65535 chars). */
    @PutMapping(
            value = "/{key}",
            consumes = {MediaType.TEXT_PLAIN_VALUE, MediaType.ALL_VALUE})
    public ResponseEntity<?> putSecret(@PathVariable String key, @RequestBody(required = false) String value) {
        ResponseEntity<?> err = validateKey(key);
        if (err != null) return err;
        if (value == null || value.isEmpty()) {
            return ResponseEntity.badRequest().body("value is required");
        }
        storeProvider.set(currentUserId(), key, value);
        log.info("AUDIT put-secret: userId={} key={}", currentUserId(), key);
        return ResponseEntity.ok().build();
    }

    /** DELETE /api/secrets/{key} — returns 200 OK (Conductor parity). */
    @DeleteMapping("/{key}")
    public ResponseEntity<?> deleteSecret(@PathVariable String key) {
        ResponseEntity<?> err = validateKey(key);
        if (err != null) return err;
        storeProvider.delete(currentUserId(), key);
        log.info("AUDIT delete-secret: userId={} key={}", currentUserId(), key);
        return ResponseEntity.ok().build();
    }

    /** GET /api/secrets/{key}/exists. */
    @GetMapping(value = "/{key}/exists", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Boolean> exists(@PathVariable String key) {
        ResponseEntity<?> err = validateKey(key);
        if (err != null) return ResponseEntity.badRequest().build();
        boolean present = storeProvider.get(currentUserId(), key) != null;
        return ResponseEntity.ok(present);
    }

    // ── Helpers ───────────────────────────────────────────────────────

    /**
     * Validates a secret key against Conductor's name rules.
     * Returns a 400 ResponseEntity if invalid, null if valid.
     */
    private ResponseEntity<?> validateKey(String key) {
        if (key == null || key.isBlank()) {
            return ResponseEntity.badRequest().body("key must not be blank");
        }
        if (key.length() > MAX_KEY_LENGTH) {
            return ResponseEntity.badRequest().body("key must be at most 65535 characters");
        }
        if (!KEY_REGEX.matcher(key).matches()) {
            return ResponseEntity.badRequest()
                    .body("key must match pattern " + KEY_PATTERN + " (alphanumeric, underscore, dash only)");
        }
        return null;
    }

    private String currentUserId() {
        return RequestContextHolder.getRequiredUser().getId();
    }
}
