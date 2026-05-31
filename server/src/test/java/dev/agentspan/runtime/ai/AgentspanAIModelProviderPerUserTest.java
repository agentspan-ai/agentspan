/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.ai;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.auth.RequestContext;
import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.auth.User;
import dev.agentspan.runtime.credentials.CredentialStoreProvider;

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

    @Autowired
    @Qualifier("credentialJdbc")
    private NamedParameterJdbcTemplate jdbc;

    private static final String USER_A = "ai-test-user-A";
    private static final String USER_B = "ai-test-user-B";
    private static final String OPENAI = "OPENAI_API_KEY";
    private static final String ANON = "00000000-0000-0000-0000-000000000000";

    private String savedAnonValue;

    @BeforeEach
    void setUp() {
        // Insert both users into the users table.
        jdbc.update(
                "INSERT OR IGNORE INTO users (id, name, username, created_at) " + "VALUES (:i, :n, :u, :t)",
                Map.of(
                        "i",
                        USER_A,
                        "n",
                        "User A",
                        "u",
                        "userA",
                        "t",
                        Instant.now().toString()));
        jdbc.update(
                "INSERT OR IGNORE INTO users (id, name, username, created_at) " + "VALUES (:i, :n, :u, :t)",
                Map.of(
                        "i",
                        USER_B,
                        "n",
                        "User B",
                        "u",
                        "userB",
                        "t",
                        Instant.now().toString()));

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
        jdbc.update("DELETE FROM users WHERE id IN (:a, :b)", Map.of("a", USER_A, "b", USER_B));
        RequestContextHolder.clear();
    }

    @Test
    void resolveUserApiKey_returnsTheCorrectUserSValue() {
        // Under user A's request context, the resolved key is user A's value.
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r-a")
                .user(new User(USER_A, "User A", null, "userA"))
                .createdAt(Instant.now())
                .build());

        String resolvedA = (String) ReflectionTestUtils.invokeMethod(provider, "resolveUserApiKey", "openai");
        assertThat(resolvedA).isEqualTo("sk-userA-12345");

        // Switch to user B's request context — must now see B's value, never A's.
        RequestContextHolder.clear();
        RequestContextHolder.set(RequestContext.builder()
                .requestId("r-b")
                .user(new User(USER_B, "User B", null, "userB"))
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
                .user(new User(USER_A, "User A", null, "userA"))
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
