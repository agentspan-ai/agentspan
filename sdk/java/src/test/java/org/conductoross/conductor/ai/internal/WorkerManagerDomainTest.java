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
 * Unit tests (server-free) for WorkerManager's domain-change rebuild signal.
 *
 * <p>Regression for the stateful-domain bug surfaced by e2e {@code
 * Suite14StatefulDomain.test_concurrent_stateful_isolation}: a tool worker was first
 * registered with <em>no</em> domain (building the runner to poll the default queue),
 * then re-registered under the per-execution {@code runId} domain. Because {@code
 * register()} early-returned for an already-known task <em>without</em> flagging a
 * rebuild, the runner kept polling the default queue while the server enqueued the
 * task under the {@code runId} domain — the task sat {@code SCHEDULED} until the run
 * timed out after 600s.
 */
class WorkerManagerDomainTest {

    /**
     * Dead address: {@code register()}'s task-def upsert fails fast and is swallowed;
     * the domain/flag bookkeeping these tests assert on happens regardless of any server.
     */
    private WorkerManager newManager() {
        return new WorkerManager(new AgentConfig(100, 1), new ConductorClient("http://localhost:1/api"));
    }

    private static final Function<Map<String, Object>, Object> NOOP = in -> null;

    @Test
    void newTaskFlagsRebuild() {
        WorkerManager wm = newManager();
        wm.register("t", NOOP, null);
        assertNull(wm.getTaskDomain("t"), "no domain registered");
        assertTrue(wm.isWorkerSetChanged(), "a brand-new task must flag a runner build");
    }

    @Test
    void domainChangeOnReregistrationFlagsRebuild() {
        WorkerManager wm = newManager();

        // 1) First registration with NO domain (what runAsync's pre-register used to do).
        wm.register("t", NOOP, null);
        wm.clearWorkerSetChangedForTest(); // simulate startAll() consuming it

        // 2) Re-register the SAME task under a per-execution runId domain.
        wm.register("t", NOOP, "run-abc123");
        assertEquals("run-abc123", wm.getTaskDomain("t"), "taskDomains must reflect the new per-execution domain");
        assertTrue(
                wm.isWorkerSetChanged(),
                "a CHANGED domain on re-registration MUST flag a rebuild — otherwise the worker "
                        + "keeps polling the default queue while the server enqueues under the domain, "
                        + "leaving the task SCHEDULED until the run times out.");
    }

    @Test
    void sameDomainReregistrationDoesNotFlagRebuild() {
        WorkerManager wm = newManager();
        wm.register("t", NOOP, "run-abc123");
        wm.clearWorkerSetChangedForTest();

        wm.register("t", NOOP, "run-abc123"); // identical domain — handler swap only
        assertFalse(
                wm.isWorkerSetChanged(),
                "re-registering with the SAME domain must NOT force a needless rebuild "
                        + "(handlers are looked up live by the running worker)");
    }

    @Test
    void clearingDomainFlagsRebuild() {
        WorkerManager wm = newManager();
        wm.register("t", NOOP, "run-abc123");
        wm.clearWorkerSetChangedForTest();

        wm.register("t", NOOP, null); // domain removed
        assertNull(wm.getTaskDomain("t"));
        assertTrue(wm.isWorkerSetChanged(), "removing a domain also changes the queue and must flag a rebuild");
    }
}
