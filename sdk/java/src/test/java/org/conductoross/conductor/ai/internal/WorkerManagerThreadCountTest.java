// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.function.Function;

import org.conductoross.conductor.ai.AgentConfig;
import org.junit.jupiter.api.Test;

import com.netflix.conductor.client.http.ConductorClient;

/**
 * Unit tests (server-free) for WorkerManager's thread-count formula.
 *
 * <p>Regression for the MIN_WORKER_THREADS=16 bug: the old formula
 * {@code max(configured, max(16, N_workers))} completely ignored the configured
 * thread count whenever there were fewer than 16 worker types. This meant that
 * {@code AgentConfig(100, 1)} always yielded 16 polling threads, producing 160
 * HTTP requests/second to a SQLite-backed server — 16× the Conductor default
 * (1000ms interval, 1 thread). Over 143 sequential agent runs this caused SQLite
 * contention that drove up server response times, which combined with infinite HTTP
 * timeouts converted transient slow responses into false 600-second timeouts.
 *
 * <p>The new formula is {@code max(configured, MIN_THREADS_PER_WORKER × N_workers)},
 * where MIN_THREADS_PER_WORKER = 1 (enough to make progress without starving). Users
 * who want more throughput increase {@code AgentConfig.workerThreadCount}.
 */
class WorkerManagerThreadCountTest {

    private static final Function<Map<String, Object>, Object> NOOP = in -> null;

    private WorkerManager newManager(int configuredThreads) {
        return new WorkerManager(
                new AgentConfig(1000, configuredThreads), // 1000ms interval, N threads
                new ConductorClient("http://localhost:1/api"));
    }

    @Test
    void configuredOneThreadRespected_withOneWorker() {
        WorkerManager wm = newManager(1);
        wm.register("t1", NOOP, null);
        // 1 worker type: floor = max(1, 1×1) = 1
        // configured = 1 → threadCount = max(1, 1) = 1
        assertEquals(
                1,
                wm.computeThreadCount(),
                "AgentConfig(_, 1) with 1 worker must yield 1 thread, not 16. "
                        + "COUNTERFACTUAL: old formula max(1, max(16,1))=16 ignored configured count.");
    }

    @Test
    void configuredOneThreadRespected_withFourWorkers() {
        WorkerManager wm = newManager(1);
        wm.register("t1", NOOP, null);
        wm.register("t2", NOOP, null);
        wm.register("t3", NOOP, null);
        wm.register("t4", NOOP, null);
        // 4 worker types: floor = max(1, 1×4) = 4 (need 1 thread per type to make progress)
        // configured = 1 → threadCount = max(1, 4) = 4 (floor wins; all types can proceed)
        assertEquals(
                4,
                wm.computeThreadCount(),
                "4 worker types need at least 4 threads so each can make progress; "
                        + "configured=1 is below the floor so floor wins.");
    }

    @Test
    void higherConfiguredCountWins() {
        WorkerManager wm = newManager(20);
        wm.register("t1", NOOP, null);
        wm.register("t2", NOOP, null);
        // 2 worker types: floor = 2; configured = 20 → threadCount = max(20, 2) = 20
        assertEquals(20, wm.computeThreadCount(), "Configured threadCount=20 > floor=2, so configured wins.");
    }

    @Test
    void threadCountNeverZero() {
        WorkerManager wm = newManager(0);
        wm.register("t1", NOOP, null);
        assertTrue(wm.computeThreadCount() >= 1, "Thread count must be at least 1 even if configured=0.");
    }
}
