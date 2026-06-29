// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.conductoross.conductor.ai.exceptions.CredentialNotFoundException;
import org.conductoross.conductor.ai.internal.CredentialContext;
import org.conductoross.conductor.ai.model.ToolContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/**
 * Unit tests for per-call credential injection: the public {@link ToolContext} read API
 * and the internal {@link CredentialContext} transport that carries resolved secrets from
 * {@code WorkerManager} to {@code ToolRegistry} on the worker thread.
 *
 * <p>Covers: reading via {@link ToolContext#getCredential(String)} /
 * {@link ToolContext#getCredentialOrNull(String)}; missing name → typed exception; the
 * credential snapshot is immutable and remains readable from a thread the tool spawns even
 * after the worker thread clears the transport; and per-thread isolation of the transport.
 */
class ToolContextCredentialsTest {

    @AfterEach
    void reset() {
        CredentialContext.clear();
    }

    // ── ToolContext read API ────────────────────────────────────────────────

    @Test
    void getCredential_returns_value() {
        ToolContext ctx = new ToolContext(null, null, null, null, Map.of("OPENAI_API_KEY", "sk-test-123"));
        assertEquals("sk-test-123", ctx.getCredential("OPENAI_API_KEY"));
        assertEquals("sk-test-123", ctx.getCredentialOrNull("OPENAI_API_KEY"));
    }

    @Test
    void getCredential_missing_throws_typed_exception() {
        ToolContext ctx = new ToolContext(null, null, null, null, Map.of("KNOWN", "v"));
        assertThrows(CredentialNotFoundException.class, () -> ctx.getCredential("UNKNOWN"));
    }

    @Test
    void getCredentialOrNull_missing_returns_null() {
        ToolContext ctx = new ToolContext(null, null, null);
        assertNull(ctx.getCredentialOrNull("ANY"));
        assertThrows(CredentialNotFoundException.class, () -> ctx.getCredential("ANY"));
    }

    @Test
    void getCredentials_view_is_immutable() {
        ToolContext ctx = new ToolContext(null, null, null, null, Map.of("A", "1", "B", "2"));
        Map<String, String> view = ctx.getCredentials();
        assertEquals(2, view.size());
        assertThrows(UnsupportedOperationException.class, () -> view.put("C", "3"));
    }

    @Test
    void snapshot_is_decoupled_from_source_map() {
        java.util.Map<String, String> src = new java.util.HashMap<>();
        src.put("A", "1");
        ToolContext ctx = new ToolContext(null, null, null, null, src);
        src.put("B", "2"); // mutate source after construction
        src.clear();
        assertEquals("1", ctx.getCredential("A"));
        assertNull(ctx.getCredentialOrNull("B"));
    }

    // ── Multi-threading ───────────────────────────────────────────────────────

    /**
     * The credential snapshot lives on the ToolContext object, not a thread-local, so a
     * thread the tool spawns can read it — and it stays valid even after the worker thread
     * that built the context clears the transport (mirrors the WorkerManager finally block).
     */
    @Test
    void credentials_readable_from_child_thread_after_transport_cleared() throws Exception {
        CredentialContext.set(Map.of("TOKEN", "secret-xyz"));
        // ToolRegistry snapshots the transport into the ToolContext on the worker thread.
        ToolContext ctx = new ToolContext(null, null, null, null, CredentialContext.current());
        CredentialContext.clear(); // worker thread's finally runs

        AtomicReference<String> seen = new AtomicReference<>();
        AtomicReference<String> transportSeen = new AtomicReference<>("UNSET");
        Thread child = new Thread(() -> {
            seen.set(ctx.getCredentialOrNull("TOKEN")); // from the context object → still valid
            transportSeen.set(CredentialContext.current().get("TOKEN")); // transport is thread-local → not visible
        });
        child.start();
        child.join(2000);

        assertEquals("secret-xyz", seen.get(), "child thread must read the credential off the ToolContext");
        assertNull(transportSeen.get(), "the thread-local transport must NOT leak into other threads");
    }

    /** Concurrent worker threads see independent transport contexts. */
    @Test
    void transport_is_isolated_per_thread() throws Exception {
        AtomicReference<String> a = new AtomicReference<>();
        AtomicReference<String> b = new AtomicReference<>();
        CountDownLatch bothSet = new CountDownLatch(2);
        CountDownLatch read = new CountDownLatch(2);

        Thread ta = new Thread(() -> {
            CredentialContext.set(Map.of("KEY", "value-A"));
            bothSet.countDown();
            try {
                bothSet.await(2, TimeUnit.SECONDS); // ensure both have set before either reads
            } catch (InterruptedException ignored) {
            }
            a.set(CredentialContext.current().get("KEY"));
            read.countDown();
            CredentialContext.clear();
        });
        Thread tb = new Thread(() -> {
            CredentialContext.set(Map.of("KEY", "value-B"));
            bothSet.countDown();
            try {
                bothSet.await(2, TimeUnit.SECONDS);
            } catch (InterruptedException ignored) {
            }
            b.set(CredentialContext.current().get("KEY"));
            read.countDown();
            CredentialContext.clear();
        });
        ta.start();
        tb.start();
        assertTrue(read.await(3, TimeUnit.SECONDS), "threads did not finish in time");

        assertEquals("value-A", a.get());
        assertEquals("value-B", b.get());
    }

    // ── Transport edge cases ────────────────────────────────────────────────

    @Test
    void transport_empty_map_clears() {
        CredentialContext.set(Map.of("X", "y"));
        CredentialContext.set(Map.of());
        assertTrue(CredentialContext.current().isEmpty());
    }

    @Test
    void transport_null_clears() {
        CredentialContext.set(Map.of("X", "y"));
        CredentialContext.set(null);
        assertTrue(CredentialContext.current().isEmpty());
    }
}
