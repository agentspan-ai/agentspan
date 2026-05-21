/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static dev.agentspan.runtime.credentials.CredentialEnvSeeder.ANONYMOUS_USER_ID;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

/**
 * Unit tests for the env-vs-stored mismatch detection added to
 * {@link CredentialEnvSeeder}.
 *
 * <p>Background: before this change the seeder logged "Credential already
 * exists in store — skipping env import" at WARN on every startup, even when
 * the env value EQUALED the stored value. Users had no signal of a real
 * mismatch — and worse, fixing the env and restarting the server did nothing
 * because the stored value wasn't compared, just preserved.</p>
 *
 * <p>After: the seeder tracks {@code lastMismatchedNames} (env value differs
 * from stored value) so callers and startup banners can surface the problem
 * visibly. Tests assert on this field instead of inspecting log output.</p>
 */
class CredentialEnvSeederMismatchTest {

    private void setStoreField(CredentialEnvSeeder seeder) throws Exception {
        var field = CredentialEnvSeeder.class.getDeclaredField("credentialsStore");
        field.setAccessible(true);
        field.set(seeder, "built-in");
    }

    @Test
    void recordsMismatchWhenEnvDiffersFromStored() throws Exception {
        CredentialStoreProvider store = mock(CredentialStoreProvider.class);
        when(store.get(eq(ANONYMOUS_USER_ID), eq("ANTHROPIC_API_KEY"))).thenReturn("sk-OLD-stored");

        Function<String, String> env = name -> "ANTHROPIC_API_KEY".equals(name) ? "sk-NEW-from-env" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(store, env);
        setStoreField(seeder);
        seeder.run(new DefaultApplicationArguments());

        assertThat(seeder.getLastMismatchedNames()).contains("ANTHROPIC_API_KEY");
    }

    @Test
    void doesNotRecordMismatchWhenEnvMatchesStored() throws Exception {
        CredentialStoreProvider store = mock(CredentialStoreProvider.class);
        when(store.get(eq(ANONYMOUS_USER_ID), eq("ANTHROPIC_API_KEY"))).thenReturn("sk-SAME-value");

        Function<String, String> env = name -> "ANTHROPIC_API_KEY".equals(name) ? "sk-SAME-value" : null;

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(store, env);
        setStoreField(seeder);
        seeder.run(new DefaultApplicationArguments());

        assertThat(seeder.getLastMismatchedNames()).doesNotContain("ANTHROPIC_API_KEY");
    }

    @Test
    void recordsMismatchAcrossMultipleProviders() throws Exception {
        CredentialStoreProvider store = mock(CredentialStoreProvider.class);
        when(store.get(anyString(), eq("OPENAI_API_KEY"))).thenReturn("sk-old-openai");
        when(store.get(anyString(), eq("ANTHROPIC_API_KEY"))).thenReturn("sk-old-anthropic");

        Function<String, String> env = name -> switch (name) {
            case "OPENAI_API_KEY" -> "sk-new-openai";
            case "ANTHROPIC_API_KEY" -> "sk-old-anthropic"; // matches — should NOT be recorded
            default -> null;
        };

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(store, env);
        setStoreField(seeder);
        seeder.run(new DefaultApplicationArguments());

        assertThat(seeder.getLastMismatchedNames())
                .contains("OPENAI_API_KEY")
                .doesNotContain("ANTHROPIC_API_KEY");
    }

    @Test
    void mismatchNamesEmptyWhenNoEnvVarsAreSet() throws Exception {
        CredentialStoreProvider store = mock(CredentialStoreProvider.class);

        CredentialEnvSeeder seeder = new CredentialEnvSeeder(store, name -> null);
        setStoreField(seeder);
        seeder.run(new DefaultApplicationArguments());

        assertThat(seeder.getLastMismatchedNames()).isEmpty();
    }
}
