/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * Manages the credentials_binding table.
 *
 * <p>Bindings are the indirection layer: user declares "when code asks for
 * GITHUB_TOKEN, use the secret stored as my-github-prod-key". This lets users
 * rename or rotate the underlying secret without changing any code.</p>
 */
@Service
public class CredentialBindingService {

    private final NamedParameterJdbcTemplate jdbc;

    public CredentialBindingService(@Qualifier("credentialJdbc") NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Resolve a logical key to a store name for a user.
     * Returns empty if no binding exists (caller uses logicalKey as store name directly).
     */
    public Optional<String> resolve(String userId, String logicalKey) {
        try {
            String storeName = jdbc.queryForObject(
                "SELECT store_name FROM credentials_binding " +
                "WHERE user_id = :uid AND logical_key = :key",
                Map.of("uid", userId, "key", logicalKey), String.class);
            return Optional.ofNullable(storeName);
        } catch (org.springframework.dao.EmptyResultDataAccessException e) {
            return Optional.empty();
        }
    }

    /** Set or update a binding (logical_key → store_name). */
    public void setBinding(String userId, String logicalKey, String storeName) {
        int updated = jdbc.update(
            "UPDATE credentials_binding SET store_name = :sn " +
            "WHERE user_id = :uid AND logical_key = :key",
            Map.of("sn", storeName, "uid", userId, "key", logicalKey));
        if (updated == 0) {
            jdbc.update(
                "INSERT INTO credentials_binding (user_id, logical_key, store_name) " +
                "VALUES (:uid, :key, :sn)",
                Map.of("uid", userId, "key", logicalKey, "sn", storeName));
        }
    }

    /** Delete a binding. No-op if not found. */
    public void deleteBinding(String userId, String logicalKey) {
        jdbc.update("DELETE FROM credentials_binding WHERE user_id = :uid AND logical_key = :key",
            Map.of("uid", userId, "key", logicalKey));
    }

    /** List all bindings for a user as a logicalKey → storeName map. */
    public Map<String, String> listBindings(String userId) {
        Map<String, String> result = new LinkedHashMap<>();
        jdbc.query(
            "SELECT logical_key, store_name FROM credentials_binding " +
            "WHERE user_id = :uid ORDER BY logical_key",
            Map.of("uid", userId),
            (ResultSetExtractor<Void>) rs -> {
                while (rs.next()) {
                    result.put(rs.getString("logical_key"), rs.getString("store_name"));
                }
                return null;
            }
        );
        return result;
    }
}
