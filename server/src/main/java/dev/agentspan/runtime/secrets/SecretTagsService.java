/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.secrets;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

import dev.agentspan.runtime.model.secrets.Tag;

/**
 * Manages the secret_tags table. Tags are key/value labels attached to a secret
 * for organization / RBAC scoping (mirrors Conductor's Tag model).
 */
@Service
public class SecretTagsService {

    private final NamedParameterJdbcTemplate jdbc;

    public SecretTagsService(@Qualifier("secretJdbc") NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Tag> list(String userId, String name) {
        List<Tag> result = new ArrayList<>();
        jdbc.query(
                "SELECT tag_key, tag_value FROM secret_tags "
                        + "WHERE user_id = :uid AND name = :name ORDER BY tag_key, tag_value",
                Map.of("uid", userId, "name", name),
                (ResultSetExtractor<Void>) rs -> {
                    while (rs.next()) {
                        result.add(new Tag(rs.getString("tag_key"), rs.getString("tag_value")));
                    }
                    return null;
                });
        return result;
    }

    public void add(String userId, String name, List<Tag> tags) {
        for (Tag t : tags) {
            if (t.getKey() == null || t.getValue() == null) continue;
            jdbc.update(
                    "INSERT INTO secret_tags (user_id, name, tag_key, tag_value) "
                            + "VALUES (:uid, :name, :k, :v) ON CONFLICT DO NOTHING",
                    Map.of("uid", userId, "name", name, "k", t.getKey(), "v", t.getValue()));
        }
    }

    public void remove(String userId, String name, List<Tag> tags) {
        for (Tag t : tags) {
            if (t.getKey() == null || t.getValue() == null) continue;
            jdbc.update(
                    "DELETE FROM secret_tags "
                            + "WHERE user_id = :uid AND name = :name AND tag_key = :k AND tag_value = :v",
                    Map.of("uid", userId, "name", name, "k", t.getKey(), "v", t.getValue()));
        }
    }

    public void removeAllForSecret(String userId, String name) {
        jdbc.update(
                "DELETE FROM secret_tags WHERE user_id = :uid AND name = :name", Map.of("uid", userId, "name", name));
    }
}
