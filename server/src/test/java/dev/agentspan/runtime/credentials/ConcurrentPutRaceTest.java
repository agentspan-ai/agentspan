/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.credentials;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import dev.agentspan.runtime.AgentRuntime;

/**
 * Regression test for Bug #3 — concurrent PUT on the same (user, name) was
 * racy under the original UPDATE-then-INSERT pattern:
 *
 * <pre>
 *   T0  Thread A: UPDATE → 0 rows (secret doesn't exist)
 *   T0  Thread B: UPDATE → 0 rows (still doesn't exist)
 *   T1  Thread A: INSERT → ok
 *   T1  Thread B: INSERT → PK violation → IllegalStateException → 500 to caller
 * </pre>
 *
 * <p>Fix: switch {@code set()} to {@code INSERT OR REPLACE} on SQLite and
 * {@code INSERT … ON CONFLICT(user_id, name) DO UPDATE SET …} on Postgres —
 * single atomic statement, no race.</p>
 */
@SpringBootTest(classes = AgentRuntime.class, webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class ConcurrentPutRaceTest {

    @Autowired
    private CredentialStoreProvider store;

    private static final String USER = "race-test-user";
    private static final String NAME = "_RACE_TEST_KEY";

    @BeforeEach
    void clean() {
        store.delete(USER, NAME);
    }

    @AfterEach
    void clean2() {
        store.delete(USER, NAME);
    }

    @Test
    void concurrentPut_newCredential_doesNotThrow() throws Exception {
        int N = 50;
        AtomicInteger errors = new AtomicInteger();
        CompletableFuture<?>[] futures = new CompletableFuture<?>[N];
        for (int i = 0; i < N; i++) {
            final int idx = i;
            futures[i] = CompletableFuture.runAsync(() -> {
                try {
                    store.set(USER, NAME, "value-" + idx);
                } catch (Throwable t) {
                    errors.incrementAndGet();
                }
            });
        }
        for (var f : futures) f.get();

        assertThat(errors.get())
                .as("Concurrent PUT on a new credential must not throw. "
                        + "Pre-fix the UPDATE-then-INSERT pattern raced on PK violation.")
                .isZero();

        // And the value is set (last writer wins; we just assert SOME write succeeded).
        assertThat(store.get(USER, NAME)).isNotNull();
    }

    @Test
    void concurrentPut_existingCredential_doesNotThrow() throws Exception {
        store.set(USER, NAME, "initial-value");

        int N = 50;
        AtomicInteger errors = new AtomicInteger();
        CompletableFuture<?>[] futures = new CompletableFuture<?>[N];
        for (int i = 0; i < N; i++) {
            final int idx = i;
            futures[i] = CompletableFuture.runAsync(() -> {
                try {
                    store.set(USER, NAME, "updated-value-" + idx);
                } catch (Throwable t) {
                    errors.incrementAndGet();
                }
            });
        }
        for (var f : futures) f.get();

        assertThat(errors.get()).isZero();
        assertThat(store.get(USER, NAME)).startsWith("updated-value-");
    }
}
