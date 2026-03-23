/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.auth;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * Manages API keys. Raw keys are shown once on creation (asp_ prefix + 32 random bytes base64).
 * Only a SHA-256 hash is stored in the DB — brute-forcing the hash space is infeasible.
 */
@Repository
public class ApiKeyRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public ApiKeyRepository(@Qualifier("credentialJdbc") NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Create a new API key for the given user.
     *
     * @return the raw key (asp_ prefix + random bytes) — shown once, not stored
     */
    public String createKey(String userId, String label) {
        byte[] random = new byte[24];
        new SecureRandom().nextBytes(random);
        String rawKey = "asp_" + Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        String hash = sha256Hex(rawKey);
        String id = UUID.randomUUID().toString();
        String now = Instant.now().toString();
        jdbc.update(
            "INSERT INTO api_keys (id, user_id, key_hash, label, created_at) " +
            "VALUES (:id, :uid, :hash, :label, :now)",
            Map.of("id", id, "uid", userId, "hash", hash, "label", label, "now", now)
        );
        return rawKey;
    }

    /**
     * Look up the User associated with a raw API key.
     * Updates last_used_at on successful lookup.
     */
    public Optional<User> findUserByKey(String rawKey) {
        String hash = sha256Hex(rawKey);
        // Two-step: first read user + key ID (connection closes after query), then update.
        // Nesting a jdbc.update() inside a RowMapper causes a connection-exhaustion deadlock
        // with single-connection pools (SQLite pool has maximumPoolSize=1).
        record Row(String uid, String name, String email, String username, String kid) {}
        Row[] found = new Row[1];
        jdbc.query(
            "SELECT u.id, u.name, u.email, u.username, k.id AS kid " +
            "FROM api_keys k JOIN users u ON k.user_id = u.id " +
            "WHERE k.key_hash = :hash",
            Map.of("hash", hash),
            (ResultSetExtractor<Void>) rs -> {
                if (rs.next()) {
                    found[0] = new Row(rs.getString("id"), rs.getString("name"),
                        rs.getString("email"), rs.getString("username"), rs.getString("kid"));
                }
                return null;
            });
        if (found[0] == null) return Optional.empty();
        jdbc.update("UPDATE api_keys SET last_used_at = :now WHERE id = :id",
            Map.of("now", Instant.now().toString(), "id", found[0].kid()));
        return Optional.of(new User(found[0].uid(), found[0].name(),
            found[0].email(), found[0].username()));
    }

    static String sha256Hex(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : hash) { hex.append(String.format("%02x", b)); }
            return hex.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
