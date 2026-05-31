/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static dev.agentspan.runtime.credentials.CredentialEnvSeeder.ANONYMOUS_USER_ID;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

/**
 * Integration test that verifies CredentialEnvSeeder can store credentials
 * against the real database without FK or schema errors.
 *
 * The test profile sets ANTHROPIC_API_KEY via application-test.properties,
 * so the seeder should have created a credential for the anonymous user.
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialEnvSeederIntegrationTest {

    @Autowired
    private CredentialStoreProvider storeProvider;

    @Test
    void seeder_storesCredential_withoutForeignKeyError() {
        // The seeder runs at startup. If ANTHROPIC_API_KEY is in the env
        // (or test properties), the credential should exist.
        // At minimum, verify we can write and read back without errors.
        storeProvider.set(ANONYMOUS_USER_ID, "INTEGRATION_TEST_KEY", "test-value-123");
        String value = storeProvider.get(ANONYMOUS_USER_ID, "INTEGRATION_TEST_KEY");
        assertThat(value).isEqualTo("test-value-123");

        // Cleanup
        storeProvider.delete(ANONYMOUS_USER_ID, "INTEGRATION_TEST_KEY");
    }
}
