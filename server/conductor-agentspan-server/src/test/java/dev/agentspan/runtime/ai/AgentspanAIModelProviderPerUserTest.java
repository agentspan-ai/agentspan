/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.context.RequestContext;
import dev.agentspan.runtime.context.RequestContextHolder;
import dev.agentspan.runtime.spi.CredentialStoreProvider;

/**
 * Audit Gap B — per-user resolution of LLM provider API keys.
 *
 * <p>Catches: cross-tenant credential leak. Two users register
 * {@code OPENAI_API_KEY} with different values; if the per-user resolution
 * path mistakenly returns user B's value while running under user A's request
 * context (off-by-one user_id binding, ThreadLocal bleed, missing user
 * filter, …), an LLM call would route through the wrong tenant.</p>
 *
 * <p>The previous test for this class was 21 lines and only verified config
 * construction — it would not catch this bug.</p>
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class AgentspanAIModelProviderPerUserTest {

    @Autowired
    private AgentspanAIModelProvider provider;

    @Autowired
    private CredentialStoreProvider store;

    private static final String USER_A = "ai-test-user-A";
    private static final String USER_B = "ai-test-user-B";
    private static final String OPENAI = "OPENAI_API_KEY";
    private static final String ANON = "00000000-0000-0000-0000-000000000000";

    private String savedAnonValue;

    @BeforeEach
    void setUp() {
        // Secrets are keyed by a userId string in credentials_store; no users table needed.
        // The CredentialEnvSeeder copies the developer/CI shell environment into
        // the anonymous user's store at startup, including OPENAI_API_KEY if
        // one is set in the shell. That seeding is the right behavior for
        // local-dev frictionlessness, but it pollutes this test which wants
        // to assert anonymous-fallback returns null. Snapshot and clear it.
        savedAnonValue = store.get(ANON, OPENAI);
        if (savedAnonValue != null) store.delete(ANON, OPENAI);

        // Same name, different values for each test user
        store.set(USER_A, OPENAI, "sk-userA-12345");
        store.set(USER_B, OPENAI, "sk-userB-67890");
    }

    @AfterEach
    void cleanUp() {
        store.delete(USER_A, OPENAI);
        store.delete(USER_B, OPENAI);
        // Restore the seeded anonymous-user value so other tests still see it.
        if (savedAnonValue != null) store.set(ANON, OPENAI, savedAnonValue);
        RequestContextHolder.clear();
    }

    @Test
    void resolveUserApiKey_returnsTheCorrectUserSValue() {
        // Under user A's request context, the resolved key is user A's value.
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r-a")
                .userId(USER_A)
                .createdAt(Instant.now())
                .build());

        String resolvedA = (String) ReflectionTestUtils.invokeMethod(provider, "resolveUserApiKey", "openai");
        assertThat(resolvedA).isEqualTo("sk-userA-12345");

        // Switch to user B's request context — must now see B's value, never A's.
        RequestContextHolder.clear();
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r-b")
                .userId(USER_B)
                .createdAt(Instant.now())
                .build());

        String resolvedB = (String) ReflectionTestUtils.invokeMethod(provider, "resolveUserApiKey", "openai");
        assertThat(resolvedB).isEqualTo("sk-userB-67890");
    }

    @Test
    void resolveUserApiKey_noRequestContext_fallsBackToAnonymousUserId() {
        // No RequestContext, no TaskContext: code falls back to anonymous UUID.
        // Anonymous has no value stored → null.
        RequestContextHolder.clear();
        String resolved = (String) ReflectionTestUtils.invokeMethod(provider, "resolveUserApiKey", "openai");
        assertThat(resolved).isNull();
    }

    @Test
    void resolveUserApiKey_unknownProvider_returnsNull() {
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r")
                .userId(USER_A)
                .createdAt(Instant.now())
                .build());

        String resolved =
                (String) ReflectionTestUtils.invokeMethod(provider, "resolveUserApiKey", "no-such-provider-xyz");
        assertThat(resolved).isNull();
    }

    // Note: an `isProviderConfigured_distinguishesUsers` test would be nice but
    // is hard to write deterministically because the test profile may have
    // openai pre-registered as a startup-configured provider depending on
    // whether the shell environment has OPENAI_API_KEY at JVM start. Per-user
    // resolution is exercised directly by the three tests above.
}
