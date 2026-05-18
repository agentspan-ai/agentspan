/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

/**
 * Integration test for CredentialResolutionService — real DB, real services, no mocks.
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialResolutionServiceTest {

    @Autowired
    private CredentialResolutionService service;

    @Autowired
    private CredentialStoreProvider storeProvider;

    @Autowired
    private CredentialBindingService bindingService;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER_ID = "resolution-test-user-001";

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM credentials_binding WHERE user_id = :uid", Map.of("uid", USER_ID));
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :uid", Map.of("uid", USER_ID));
    }

    @Test
    void resolve_directLookup_returnsStoredValue() {
        storeProvider.set(USER_ID, "GITHUB_TOKEN", "ghp_directlookup");

        String value = service.resolve(USER_ID, "GITHUB_TOKEN");

        assertThat(value).isEqualTo("ghp_directlookup");
    }

    @Test
    void resolve_withBinding_usesStoreName() {
        storeProvider.set(USER_ID, "my-github-prod", "ghp_bound_secret");
        bindingService.setBinding(USER_ID, "GITHUB_TOKEN", "my-github-prod");

        String value = service.resolve(USER_ID, "GITHUB_TOKEN");

        assertThat(value).isEqualTo("ghp_bound_secret");
    }

    @Test
    void resolve_notInStore_returnsNull() {
        String value = service.resolve(USER_ID, "TOTALLY_MISSING_KEY_XYZ");

        assertThat(value).isNull();
    }

    @Test
    void resolve_notInStore_noEnvFallback() {
        // PATH exists in every process environment, but the server should NOT
        // fall back to env vars — the store is the source of truth.
        String value = service.resolve(USER_ID, "PATH");

        assertThat(value).isNull();
    }

    @Test
    void resolve_afterDelete_returnsNull() {
        storeProvider.set(USER_ID, "TEMP_KEY", "temp_value");
        assertThat(service.resolve(USER_ID, "TEMP_KEY")).isEqualTo("temp_value");

        storeProvider.delete(USER_ID, "TEMP_KEY");
        assertThat(service.resolve(USER_ID, "TEMP_KEY")).isNull();
    }
}
