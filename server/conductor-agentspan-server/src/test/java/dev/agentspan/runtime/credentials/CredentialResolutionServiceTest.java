/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.*;

import java.util.Map;

import org.conductoross.conductor.dao.SecretsDAO;
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
    private SecretsDAO storeProvider;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER_ID = "00000000-0000-0000-0000-000000000000";

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :uid", Map.of("uid", USER_ID));
    }

    @Test
    void resolve_directLookup_returnsStoredValue() {
        storeProvider.putSecret("GITHUB_TOKEN", "ghp_directlookup");

        String value = service.resolve("GITHUB_TOKEN");

        assertThat(value).isEqualTo("ghp_directlookup");
    }

    @Test
    void resolve_notInStore_returnsNull() {
        String value = service.resolve("TOTALLY_MISSING_KEY_XYZ");

        assertThat(value).isNull();
    }

    @Test
    void resolve_notInStore_noEnvFallback() {
        // PATH exists in every process environment, but the server should NOT
        // fall back to env vars — the store is the source of truth.
        String value = service.resolve("PATH");

        assertThat(value).isNull();
    }

    @Test
    void resolve_afterDelete_returnsNull() {
        storeProvider.putSecret("TEMP_KEY", "temp_value");
        assertThat(service.resolve("TEMP_KEY")).isEqualTo("temp_value");

        storeProvider.deleteSecret("TEMP_KEY");
        assertThat(service.resolve("TEMP_KEY")).isNull();
    }

    // ── JSONPath (Conductor-parity dotted-path extraction) ─────────────

    @Test
    void resolve_dottedPath_extractsTopLevelField() {
        storeProvider.putSecret(
                "GCP_SVC",
                "{\"type\":\"service_account\",\"project_id\":\"my-proj-123\",\"client_email\":\"sa@x.iam\"}");

        assertThat(service.resolve("GCP_SVC.project_id")).isEqualTo("my-proj-123");
        assertThat(service.resolve("GCP_SVC.type")).isEqualTo("service_account");
    }

    @Test
    void resolve_dottedPath_extractsNestedField() {
        storeProvider.putSecret("BLOB", "{\"auth\":{\"oauth\":{\"client_id\":\"abc123\"}}}");

        assertThat(service.resolve("BLOB.auth.oauth.client_id")).isEqualTo("abc123");
    }

    @Test
    void resolve_dottedPath_missingField_returnsNull() {
        storeProvider.putSecret("JSONY", "{\"a\":\"1\",\"b\":\"2\"}");

        assertThat(service.resolve("JSONY.does_not_exist")).isNull();
    }

    @Test
    void resolve_dottedPath_baseCredentialMissing_returnsNull() {
        // Base credential doesn't exist at all
        assertThat(service.resolve("DOES_NOT_EXIST.anything")).isNull();
    }

    @Test
    void resolve_dottedPath_nonJsonBase_returnsNull() {
        storeProvider.putSecret("FLAT_TOKEN", "not-a-json-value-just-text");

        assertThat(service.resolve("FLAT_TOKEN.field")).isNull();
    }

    @Test
    void resolve_dottedPath_nonStringLeaf_returnsJsonRepresentation() {
        // Number/boolean/object leaves serialize to their JSON form so HTTP/MCP
        // placeholders can substitute them cleanly.
        storeProvider.putSecret("CFG", "{\"port\":8080,\"enabled\":true,\"nested\":{\"a\":1}}");

        assertThat(service.resolve("CFG.port")).isEqualTo("8080");
        assertThat(service.resolve("CFG.enabled")).isEqualTo("true");
        // Object leaves come back as compact JSON
        assertThat(service.resolve("CFG.nested")).isEqualTo("{\"a\":1}");
    }

    @Test
    void resolve_dottedPath_doesNotFallthroughToFullName() {
        // Even if a literal-dotted name happens to be stored, dotted resolution
        // ALWAYS treats the first segment as the base. Documented constraint.
        storeProvider.putSecret("LITERAL.NAME", "literally_dotted_value");
        storeProvider.putSecret("LITERAL", "{\"NAME\":\"json_value\"}");

        assertThat(service.resolve("LITERAL.NAME")).isEqualTo("json_value");
    }
}
