/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.model.secrets.SecretMeta;
import dev.agentspan.runtime.model.secrets.Tag;
import dev.agentspan.runtime.secrets.SecretStoreProvider;
import dev.agentspan.runtime.secrets.SecretTagsService;

import lombok.RequiredArgsConstructor;

/**
 * REST controller for secrets — Conductor-parity contract.
 *
 * <p>Mirrors {@code io.orkes.conductor.server.rest.SecretResource} (v1) and
 * {@code SecretResourceV2}. Auth: every endpoint here requires a logged-in
 * session (login JWT or API key, set by {@link dev.agentspan.runtime.auth.AuthFilter}).</p>
 *
 * <p>The token-mediated worker fetch endpoint (no Conductor equivalent) lives in
 * {@link WorkerController} at {@code POST /api/workers/secrets} — separate
 * namespace because it uses a different auth primitive (execution token).</p>
 *
 * <ul>
 *   <li>{@code POST   /api/secrets}              — list names ({@code List<String>})</li>
 *   <li>{@code GET    /api/secrets}              — list names user can grant access to</li>
 *   <li>{@code GET    /api/secrets/v2}           — richer metadata (name, partial, timestamps, tags)</li>
 *   <li>{@code GET    /api/secrets/{key}}        — plaintext value (text/plain)</li>
 *   <li>{@code PUT    /api/secrets/{key}}        — upsert; raw-string body</li>
 *   <li>{@code DELETE /api/secrets/{key}}        — delete</li>
 *   <li>{@code GET    /api/secrets/{key}/exists} — boolean</li>
 *   <li>{@code GET    /api/secrets/{key}/tags}   — list tags</li>
 *   <li>{@code PUT    /api/secrets/{key}/tags}   — add tags</li>
 *   <li>{@code DELETE /api/secrets/{key}/tags}   — remove tags</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/secrets")
@RequiredArgsConstructor
public class SecretController {

    private static final Logger log = LoggerFactory.getLogger(SecretController.class);

    private final SecretStoreProvider storeProvider;
    private final SecretTagsService tagsService;

    // ── List ──────────────────────────────────────────────────────────

    /** POST /api/secrets — list all secret names (Conductor's primary listing endpoint). */
    @PostMapping
    public ResponseEntity<List<String>> listAllNames() {
        List<String> names = storeProvider.list(currentUserId()).stream()
                .map(SecretMeta::getName)
                .toList();
        return ResponseEntity.ok(names);
    }

    /**
     * GET /api/secrets — list secrets the caller can grant access to.
     * <p>In OSS (no RBAC) this returns the same set as POST. Enterprise filters
     * by the user's grant permissions.</p>
     */
    @GetMapping
    public ResponseEntity<List<String>> listGrantable() {
        return listAllNames();
    }

    /**
     * GET /api/secrets/v2 — list with full metadata (mirrors Conductor's SecretResourceV2).
     * <p>Returns name + partial value + timestamps + tags. Used by the UI.</p>
     */
    @GetMapping("/v2")
    public ResponseEntity<List<SecretMeta>> listWithMeta() {
        String userId = currentUserId();
        List<SecretMeta> list = storeProvider.list(userId);
        for (SecretMeta m : list) {
            m.setTags(tagsService.list(userId, m.getName()));
        }
        return ResponseEntity.ok(list);
    }

    // ── Value CRUD ────────────────────────────────────────────────────

    /** GET /api/secrets/{key} — plaintext value. */
    @GetMapping(value = "/{key}", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> getSecret(@PathVariable String key) {
        String value = storeProvider.get(currentUserId(), key);
        log.info("AUDIT get-secret: userId={} key={} found={}", currentUserId(), key, value != null);
        if (value == null) return ResponseEntity.notFound().build();
        return ResponseEntity.ok(value);
    }

    /** PUT /api/secrets/{key} — upsert; body is the raw secret value. */
    @PutMapping(
            value = "/{key}",
            consumes = {MediaType.TEXT_PLAIN_VALUE, MediaType.ALL_VALUE})
    public ResponseEntity<?> putSecret(@PathVariable String key, @RequestBody String value) {
        if (value == null || value.isEmpty()) {
            return ResponseEntity.badRequest().body("value is required");
        }
        storeProvider.set(currentUserId(), key, value);
        log.info("AUDIT put-secret: userId={} key={}", currentUserId(), key);
        return ResponseEntity.ok().build();
    }

    /** DELETE /api/secrets/{key}. */
    @DeleteMapping("/{key}")
    public ResponseEntity<?> deleteSecret(@PathVariable String key) {
        String userId = currentUserId();
        storeProvider.delete(userId, key);
        tagsService.removeAllForSecret(userId, key);
        log.info("AUDIT delete-secret: userId={} key={}", userId, key);
        return ResponseEntity.noContent().build();
    }

    /** GET /api/secrets/{key}/exists. */
    @GetMapping(value = "/{key}/exists", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Boolean> exists(@PathVariable String key) {
        boolean present = storeProvider.get(currentUserId(), key) != null;
        return ResponseEntity.ok(present);
    }

    // ── Tags ──────────────────────────────────────────────────────────

    /** GET /api/secrets/{key}/tags. */
    @GetMapping("/{key}/tags")
    public ResponseEntity<List<Tag>> getTags(@PathVariable String key) {
        return ResponseEntity.ok(tagsService.list(currentUserId(), key));
    }

    /** PUT /api/secrets/{key}/tags — add tags. */
    @PutMapping("/{key}/tags")
    public ResponseEntity<?> putTags(@PathVariable String key, @RequestBody List<Tag> tags) {
        tagsService.add(currentUserId(), key, tags);
        return ResponseEntity.ok().build();
    }

    /** DELETE /api/secrets/{key}/tags — remove tags. */
    @DeleteMapping("/{key}/tags")
    public ResponseEntity<?> deleteTags(@PathVariable String key, @RequestBody List<Tag> tags) {
        tagsService.remove(currentUserId(), key, tags);
        return ResponseEntity.ok().build();
    }

    // ── Helpers ───────────────────────────────────────────────────────

    private String currentUserId() {
        return RequestContextHolder.getRequiredUser().getId();
    }
}
