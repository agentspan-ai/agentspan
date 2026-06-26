/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;
import dev.agentspan.runtime.context.RequestContext;
import dev.agentspan.runtime.context.RequestContextHolder;
import dev.agentspan.runtime.spi.CredentialStoreProvider;

/**
 * {@code SecretController} list endpoints filter by principal.
 *
 * <p>{@code CredentialControllerTest} drives {@code /api/secrets} through MockMvc, but the
 * {@code AuthFilter} forces every request onto the single anonymous user, so it can't observe
 * per-principal scoping. This test wires the real {@code SecretController} +
 * {@code CredentialStoreProvider} and sets {@code RequestContextHolder} to two distinct
 * principals directly — the only way to assert the listing isolation property in OSS.</p>
 *
 * <p>The property under test: {@code listGrantable()} (GET) and {@code listAllNames()} (POST)
 * call {@code storeProvider.list(currentUserId())}, so user A must never see user B's secret
 * names. Catches a regression where {@code currentUserId()} is bypassed or the store query drops
 * its {@code WHERE user_id} scoping.</p>
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class SecretControllerScopingTest {

    @Autowired
    private SecretController controller;

    @Autowired
    private CredentialStoreProvider store;

    private static final String USER_A = "secret-scope-user-A";
    private static final String USER_B = "secret-scope-user-B";

    // Non-seeded names so CredentialEnvSeeder doesn't populate them for the anonymous user.
    private static final String A_KEY = "_SCOPE_TEST_KEY_A";
    private static final String B_KEY = "_SCOPE_TEST_KEY_B";

    @BeforeEach
    void setUp() {
        store.set(USER_A, A_KEY, "value-A");
        store.set(USER_B, B_KEY, "value-B");
    }

    @AfterEach
    void tearDown() {
        store.delete(USER_A, A_KEY);
        store.delete(USER_B, B_KEY);
        RequestContextHolder.clear();
    }

    private void actAs(String userId) {
        RequestContextHolder.set(RequestContext.builder()
                .requestId("req-" + userId)
                .userId(userId)
                .createdAt(Instant.now())
                .build());
    }

    // ── GET /api/secrets (listGrantable) ───────────────────────────────

    @Test
    void listGrantable_returnsOnlyCallersOwnNames() {
        actAs(USER_A);
        Set<String> namesA = controller.listGrantable().getBody();
        assertThat(namesA).contains(A_KEY);
        assertThat(namesA).doesNotContain(B_KEY);

        actAs(USER_B);
        Set<String> namesB = controller.listGrantable().getBody();
        assertThat(namesB).contains(B_KEY);
        assertThat(namesB).doesNotContain(A_KEY);
    }

    // ── POST /api/secrets (listAllNames) ───────────────────────────────

    @Test
    void listAllNames_returnsOnlyCallersOwnNames() {
        actAs(USER_A);
        List<String> namesA = controller.listAllNames().getBody();
        assertThat(namesA).contains(A_KEY);
        assertThat(namesA).doesNotContain(B_KEY);

        actAs(USER_B);
        List<String> namesB = controller.listAllNames().getBody();
        assertThat(namesB).contains(B_KEY);
        assertThat(namesB).doesNotContain(A_KEY);
    }
}
