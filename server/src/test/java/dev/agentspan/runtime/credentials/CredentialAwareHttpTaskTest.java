/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.conductoross.conductor.AgentRuntime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;

/**
 * Integration test for CredentialAwareHttpTask — real DB, real credential store.
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialAwareHttpTaskTest {

    @Autowired
    private CredentialStoreProvider storeProvider;

    @Autowired
    private CredentialAwareHttpTask httpTask;

    private static final String USER_ID = "http-task-test-user";

    @BeforeEach
    void setUp() {
        storeProvider.set(USER_ID, "MY_API_KEY", "resolved-secret-value");
    }

    @Test
    void resolveHeaders_substitutesPlaceholders() {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Bearer ${MY_API_KEY}");
        headers.put("X-Static", "no-placeholder");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Authorization")).isEqualTo("Bearer resolved-secret-value");
        assertThat(resolved.get("X-Static")).isEqualTo("no-placeholder");
    }

    @Test
    void resolveHeaders_unresolvedPlaceholder_replacedWithEmpty() {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Bearer ${NONEXISTENT}");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Authorization")).isEqualTo("Bearer ");
    }

    @Test
    void resolveHeaders_noPlaceholders_returnsUnchanged() {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("X-Static", "value");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("X-Static")).isEqualTo("value");
    }

    @Test
    void resolveHeaders_credentialValueWithDollarSign_handledSafely() {
        storeProvider.set(USER_ID, "TRICKY_KEY", "val$with$dollars");

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Auth", "${TRICKY_KEY}");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Auth")).isEqualTo("val$with$dollars");
    }

    @Test
    void resolveHeaders_multiplePlaceholders_inSameHeader() {
        storeProvider.set(USER_ID, "USER", "admin");
        storeProvider.set(USER_ID, "PASS", "secret123");

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Basic ${USER}:${PASS}");

        Map<String, String> resolved = httpTask.resolveHeadersForUser(headers, USER_ID);

        assertThat(resolved.get("Authorization")).isEqualTo("Basic admin:secret123");
    }
}
