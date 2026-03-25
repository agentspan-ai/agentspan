/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import dev.agentspan.runtime.AgentRuntime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.util.Map;
import java.util.function.Function;

import static dev.agentspan.runtime.credentials.CredentialEnvSeeder.ANONYMOUS_USER_ID;
import static org.assertj.core.api.Assertions.*;

/**
 * Integration test for CredentialEnvSeeder — uses real DB, no mocks.
 * The test profile provides AGENTSPAN_MASTER_KEY and a real SQLite DB.
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CredentialEnvSeederTest {

    @Autowired
    private CredentialStoreProvider storeProvider;

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    @BeforeEach
    void cleanUp() {
        // Remove test credentials from previous runs
        jdbc.update("DELETE FROM credentials_store WHERE user_id = :uid AND name LIKE '_TEST_%'",
            Map.of("uid", ANONYMOUS_USER_ID));
    }

    @Test
    void seeder_storesCredentialFromEnv_inRealDb() throws Exception {
        // Simulate env with a test key
        Function<String, String> fakeEnv = name ->
            "_TEST_ANTHROPIC_KEY".equals(name) ? "sk-test-value" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, fakeEnv);
        // Override known vars for this test
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        // The seeder won't find _TEST_ANTHROPIC_KEY in KNOWN_ENV_VARS,
        // so let's test with a real known var by injecting via the env lookup
        Function<String, String> envWithAnthropicKey = name ->
            "ANTHROPIC_API_KEY".equals(name) ? "sk-test-seeded-value" : null;

        CredentialEnvSeeder realSeeder = new CredentialEnvSeeder(storeProvider, envWithAnthropicKey);
        field.set(realSeeder, "built-in");

        // Delete existing credential first so seeder can create it
        storeProvider.delete(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");

        realSeeder.run(new org.springframework.boot.DefaultApplicationArguments());

        // Verify credential was stored in real DB
        String value = storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        assertThat(value).isEqualTo("sk-test-seeded-value");
    }

    @Test
    void seeder_skipsExistingCredential_inRealDb() throws Exception {
        // Store a credential first
        storeProvider.set(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY", "original-value");

        // Try to seed with a different value
        Function<String, String> envLookup = name ->
            "ANTHROPIC_API_KEY".equals(name) ? "new-value-should-not-overwrite" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        seeder.run(new org.springframework.boot.DefaultApplicationArguments());

        // Value should still be the original
        String value = storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        assertThat(value).isEqualTo("original-value");
    }

    @Test
    void seeder_ignoresBlankEnvVars_inRealDb() throws Exception {
        // Delete so we can detect if seeder creates it
        storeProvider.delete(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");

        Function<String, String> envLookup = name ->
            "ANTHROPIC_API_KEY".equals(name) ? "   " : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        seeder.run(new org.springframework.boot.DefaultApplicationArguments());

        // Blank value should NOT be stored
        String value = storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        assertThat(value).isNull();
    }

    @Test
    void seeder_skipsWhenStoreIsNotBuiltIn() throws Exception {
        storeProvider.delete(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");

        Function<String, String> envLookup = name ->
            "ANTHROPIC_API_KEY".equals(name) ? "sk-should-not-store" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "vault");

        seeder.run(new org.springframework.boot.DefaultApplicationArguments());

        String value = storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        assertThat(value).isNull();
    }
}
