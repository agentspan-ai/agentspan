/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;

import static dev.agentspan.runtime.credentials.CredentialEnvSeeder.ANONYMOUS_USER_ID;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CredentialEnvSeederTest {

    @Mock
    private CredentialStoreProvider storeProvider;

    /** Build a seeder with a fixed env map and store=built-in. */
    private CredentialEnvSeeder seeder(Map<String, String> env) {
        CredentialEnvSeeder s = new CredentialEnvSeeder(storeProvider, env::get);
        ReflectionTestUtils.setField(s, "credentialsStore", "built-in");
        return s;
    }

    // ── Happy path ────────────────────────────────────────────────────

    @Test
    void createsCredentialWhenEnvVarSetAndNotInStore() throws Exception {
        when(storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY")).thenReturn(null);

        seeder(Map.of("ANTHROPIC_API_KEY", "sk-ant-test")).run(new DefaultApplicationArguments());

        verify(storeProvider).set(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY", "sk-ant-test");
    }

    @Test
    void skipsCredentialWhenAlreadyInStore() throws Exception {
        when(storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY")).thenReturn("existing");

        seeder(Map.of("ANTHROPIC_API_KEY", "sk-ant-new")).run(new DefaultApplicationArguments());

        verify(storeProvider, never()).set(any(), eq("ANTHROPIC_API_KEY"), any());
    }

    @Test
    void seedsMultipleEnvVarsInOnePass() throws Exception {
        when(storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY")).thenReturn(null);
        when(storeProvider.get(ANONYMOUS_USER_ID, "OPENAI_API_KEY")).thenReturn(null);

        seeder(Map.of("ANTHROPIC_API_KEY", "sk-ant", "OPENAI_API_KEY", "sk-oai"))
                .run(new DefaultApplicationArguments());

        verify(storeProvider).set(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY", "sk-ant");
        verify(storeProvider).set(ANONYMOUS_USER_ID, "OPENAI_API_KEY", "sk-oai");
    }

    // ── Env var absent / blank ────────────────────────────────────────

    @Test
    void ignoresUnsetEnvVars() throws Exception {
        seeder(Map.of()).run(new DefaultApplicationArguments());

        verifyNoInteractions(storeProvider);
    }

    @Test
    void ignoresBlankEnvVars() throws Exception {
        seeder(Map.of("ANTHROPIC_API_KEY", "  ")).run(new DefaultApplicationArguments());

        verifyNoInteractions(storeProvider);
    }

    // ── Non-built-in store ────────────────────────────────────────────

    @Test
    void skipsEntirelyWhenStoreIsNotBuiltIn() throws Exception {
        CredentialEnvSeeder s = new CredentialEnvSeeder(storeProvider, Map.of("ANTHROPIC_API_KEY", "x")::get);
        ReflectionTestUtils.setField(s, "credentialsStore", "vault");

        s.run(new DefaultApplicationArguments());

        verifyNoInteractions(storeProvider);
    }

    // ── Mixed scenario ────────────────────────────────────────────────

    @Test
    void createsNewOnesAndSkipsExisting() throws Exception {
        when(storeProvider.get(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY")).thenReturn(null);
        when(storeProvider.get(ANONYMOUS_USER_ID, "OPENAI_API_KEY")).thenReturn("already-here");

        seeder(Map.of("ANTHROPIC_API_KEY", "sk-ant-new", "OPENAI_API_KEY", "sk-oai-existing"))
                .run(new DefaultApplicationArguments());

        verify(storeProvider).set(ANONYMOUS_USER_ID, "ANTHROPIC_API_KEY", "sk-ant-new");
        verify(storeProvider, never()).set(any(), eq("OPENAI_API_KEY"), any());
    }
}
