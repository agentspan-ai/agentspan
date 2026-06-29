// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

/**
 * Unit tests for {@link WorkerManager#effectiveTaskTimeout(int)} — the rule that
 * sizes a Conductor task def's timeout/responseTimeout to a handler's configured
 * blocking timeout so the server's patience can never drift below the worker's.
 */
class WorkerManagerTimeoutTest {

    @Test
    void unconfigured_uses_safe_default() {
        assertEquals(300, WorkerManager.effectiveTaskTimeout(0), "0 (unset) must fall back to the 300s default");
        assertEquals(300, WorkerManager.effectiveTaskTimeout(-5), "negative must fall back to the 300s default");
    }

    @Test
    void short_timeouts_keep_the_300s_floor() {
        assertEquals(300, WorkerManager.effectiveTaskTimeout(30));
        assertEquals(300, WorkerManager.effectiveTaskTimeout(240)); // 240 + 60 == 300
    }

    @Test
    void long_timeouts_raise_the_ceiling_above_300_with_slack() {
        assertEquals(301, WorkerManager.effectiveTaskTimeout(241)); // 241 + 60
        assertEquals(360, WorkerManager.effectiveTaskTimeout(300)); // 300 + 60
        assertEquals(660, WorkerManager.effectiveTaskTimeout(600)); // 600 + 60
    }

    @Test
    void server_patience_always_exceeds_the_handler_timeout() {
        for (int t : new int[] {1, 100, 300, 1000, 5000}) {
            assertTrue(
                    WorkerManager.effectiveTaskTimeout(t) >= t + WorkerManager.TASK_TIMEOUT_SLACK_SECONDS,
                    "effective timeout for " + t + "s must leave at least the slack margin");
        }
    }
}
