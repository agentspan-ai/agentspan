/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialBindingServiceTest {

    @Autowired
    private CredentialBindingService bindingService;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER_ID = "binding-test-user-002";

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM credentials_binding WHERE user_id = :uid", Map.of("uid", USER_ID));
        // Portable upsert: update first; insert only if the user row doesn't exist yet.
        // Avoids SQLite-specific "INSERT OR IGNORE" and "datetime('now')" syntax.
        int updated = jdbc.update(
                "UPDATE users SET name = 'Binding Test' WHERE id = :id",
                Map.of("id", USER_ID));
        if (updated == 0) {
            jdbc.update(
                    "INSERT INTO users (id, name, email, username, password_hash, created_at) "
                            + "VALUES (:id, 'Binding Test', '', 'binding_test_user', '', :now)",
                    Map.of("id", USER_ID, "now", Instant.now().toString()));
        }
    }

    @Test
    void resolve_returnsEmpty_whenNoBinding() {
        assertThat(bindingService.resolve(USER_ID, "GITHUB_TOKEN")).isEmpty();
    }

    @Test
    void setBinding_andResolve_returnsStoreName() {
        bindingService.setBinding(USER_ID, "GITHUB_TOKEN", "my-github-prod");

        Optional<String> storeName = bindingService.resolve(USER_ID, "GITHUB_TOKEN");

        assertThat(storeName).contains("my-github-prod");
    }

    @Test
    void setBinding_updates_existingBinding() {
        bindingService.setBinding(USER_ID, "GITHUB_TOKEN", "old-name");
        bindingService.setBinding(USER_ID, "GITHUB_TOKEN", "new-name");

        assertThat(bindingService.resolve(USER_ID, "GITHUB_TOKEN")).contains("new-name");
    }

    @Test
    void deleteBinding_removesBinding() {
        bindingService.setBinding(USER_ID, "GITHUB_TOKEN", "my-key");
        bindingService.deleteBinding(USER_ID, "GITHUB_TOKEN");

        assertThat(bindingService.resolve(USER_ID, "GITHUB_TOKEN")).isEmpty();
    }

    @Test
    void listBindings_returnsAllBindings() {
        bindingService.setBinding(USER_ID, "KEY_A", "store-a");
        bindingService.setBinding(USER_ID, "KEY_B", "store-b");

        var bindings = bindingService.listBindings(USER_ID);

        assertThat(bindings).containsEntry("KEY_A", "store-a").containsEntry("KEY_B", "store-b");
    }
}
