/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static dev.agentspan.runtime.credentials.CredentialEnvSeeder.ANONYMOUS_USER_ID;
import static org.assertj.core.api.Assertions.*;

import java.util.Map;
import java.util.function.Function;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

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
        // Remove test credentials from previous runs.
        // Use ESCAPE so that the leading underscore is treated as a literal
        // character, not a single-character wildcard (SQLite/SQL standard).
        // Also guard against the table not yet existing on the very first run.
        try {
            jdbc.update(
                    "DELETE FROM credentials_store WHERE user_id = :uid AND name LIKE '\\_TEST\\_%' ESCAPE '\\'",
                    Map.of("uid", ANONYMOUS_USER_ID));
        } catch (Exception ignored) {
            // Table may not exist yet on the first test run — safe to ignore.
        }
        storeProvider.delete(ANONYMOUS_USER_ID, "GH_TOKEN");
        storeProvider.delete(ANONYMOUS_USER_ID, "GITHUB_TOKEN");
    }

    @Test
    void seeder_storesCredentialFromEnv_inRealDb() throws Exception {
        // Simulate env with a test key
        Function<String, String> fakeEnv = name -> "_TEST_ANTHROPIC_KEY".equals(name) ? "sk-test-value" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, fakeEnv);
        // Override known vars for this test
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        // The seeder won't find _TEST_ANTHROPIC_KEY in KNOWN_ENV_VARS,
        // so let's test with a real known var by injecting via the env lookup
        Function<String, String> envWithAnthropicKey =
                name -> "ANTHROPIC_API_KEY".equals(name) ? "sk-test-seeded-value" : null;

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
        Function<String, String> envLookup =
                name -> "ANTHROPIC_API_KEY".equals(name) ? "new-value-should-not-overwrite" : null;

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

        Function<String, String> envLookup = name -> "ANTHROPIC_API_KEY".equals(name) ? "   " : null;

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

        Function<String, String> envLookup = name -> "ANTHROPIC_API_KEY".equals(name) ? "sk-should-not-store" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "vault");

        seeder.run(new org.springframework.boot.DefaultApplicationArguments());

        String value = storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        assertThat(value).isNull();
    }

    @Test
    void seeder_reseeds_whenDecryptionFailsDueToKeyMismatch() throws Exception {
        // Simulate a credential encrypted with an old/rotated master key by writing
        // garbage bytes directly into the DB — decryption will throw AEADBadTagException.
        storeProvider.delete(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        String now = java.time.Instant.now().toString();
        // 12-byte fake IV + 17 bytes of garbage ciphertext → GCM tag mismatch on decrypt
        byte[] staleBytes = new byte[29];
        java.util.Arrays.fill(staleBytes, (byte) 0x42);
        jdbc.update(
                "INSERT INTO credentials_store (user_id, name, encrypted_value, created_at, updated_at) "
                        + "VALUES (:uid, :n, :enc, :now, :now)",
                Map.of("uid", ANONYMOUS_USER_ID, "n", "ANTHROPIC_API_KEY", "enc", staleBytes, "now", now));

        Function<String, String> envLookup =
                name -> "ANTHROPIC_API_KEY".equals(name) ? "sk-fresh-after-rotation" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        // Must NOT throw — seeder should self-heal instead of crashing the server
        assertThatCode(() -> seeder.run(new org.springframework.boot.DefaultApplicationArguments()))
                .doesNotThrowAnyException();

        // Credential must be re-encrypted with the current key and readable
        String value = storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY");
        assertThat(value).isEqualTo("sk-fresh-after-rotation");
    }

    @Test
    void seeder_propagates_nonDecryptionExceptions() throws Exception {
        // A non-AEADBadTagException from get() must propagate — e.g. a transient DB failure
        // should NOT silently delete a valid credential.
        CredentialStoreProvider failingStore = new CredentialStoreProvider() {
            @Override
            public String get(String userId, String name) {
                throw new IllegalStateException("DB connection lost", new RuntimeException("timeout"));
            }

            @Override
            public void set(String userId, String name, String value) {}

            @Override
            public void delete(String userId, String name) {}

            @Override
            public java.util.List<dev.agentspan.runtime.model.credentials.CredentialMeta> list(String userId) {
                return java.util.List.of();
            }
        };

        Function<String, String> envLookup = name -> "ANTHROPIC_API_KEY".equals(name) ? "sk-value" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(failingStore, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        // Non-key-mismatch exception must propagate — seeder should NOT swallow it
        assertThatThrownBy(() -> seeder.run(new org.springframework.boot.DefaultApplicationArguments()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("DB connection lost");
    }

    @Test
    void seeder_storesGitHubCredentials_inRealDb() throws Exception {
        Function<String, String> envLookup = name -> switch (name) {
            case "GH_TOKEN" -> "ghp-test-gh-token";
            case "GITHUB_TOKEN" -> "ghp-test-github-token";
            default -> null;
        };

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(storeProvider, envLookup);
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");

        seeder.run(new org.springframework.boot.DefaultApplicationArguments());

        assertThat(storeProvider.get(ANONYMOUS_USER_ID, "GH_TOKEN")).isEqualTo("ghp-test-gh-token");
        assertThat(storeProvider.get(ANONYMOUS_USER_ID, "GITHUB_TOKEN")).isEqualTo("ghp-test-github-token");
    }
}
