/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package org.conductoross.conductor.ai.internal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

import com.netflix.conductor.common.metadata.tasks.Task;

/**
 * Validates {@code WorkerManager.readRuntimeMetadata} — the ONLY credential-delivery read-path.
 * The conductor core resolves the worker's declared {@code TaskDef.runtimeMetadata} names at poll
 * time and delivers the values on the wire-only {@code Task.runtimeMetadata} (conductor-oss PR
 * #1255); there is no server endpoint to pull from.
 *
 * <p>The read is reflective because the published conductor-client's {@code Task} does not carry
 * the field yet: against today's client it returns an empty map (also covered here), and it lights
 * up automatically once the client ships {@code getRuntimeMetadata()} — simulated with a {@code
 * Task} subclass exposing the accessor.</p>
 */
class ReadRuntimeMetadataTest {

    /** Simulates a conductor-client Task model that carries the runtimeMetadata field. */
    static class TaskWithRuntimeMetadata extends Task {
        private final Map<String, Object> runtimeMetadata;

        TaskWithRuntimeMetadata(Map<String, Object> runtimeMetadata) {
            this.runtimeMetadata = runtimeMetadata;
        }

        public Map<String, Object> getRuntimeMetadata() {
            return runtimeMetadata;
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, String> invoke(Task task) throws Exception {
        Method m = WorkerManager.class.getDeclaredMethod("readRuntimeMetadata", Task.class);
        m.setAccessible(true);
        return (Map<String, String>) m.invoke(null, task);
    }

    @Test
    void extractsHostDeliveredValues() throws Exception {
        Map<String, Object> rm = new HashMap<>();
        rm.put("GITHUB_TOKEN", "ghp_host");
        rm.put("GH_APP_ID", "42");
        rm.put("NOT_A_STRING", 7); // non-string values are skipped

        Map<String, String> out = invoke(new TaskWithRuntimeMetadata(rm));

        assertEquals(2, out.size());
        assertEquals("ghp_host", out.get("GITHUB_TOKEN"));
        assertEquals("42", out.get("GH_APP_ID"));
    }

    @Test
    void emptyWhenAbsentOrEmpty() throws Exception {
        assertTrue(invoke(null).isEmpty());
        assertTrue(invoke(new TaskWithRuntimeMetadata(null)).isEmpty());
        assertTrue(invoke(new TaskWithRuntimeMetadata(new HashMap<>())).isEmpty());
    }

    @Test
    void emptyAgainstPublishedClientWithoutTheField() throws Exception {
        // The published conductor-client Task has no getRuntimeMetadata(): the reflective
        // read must degrade to an empty map, not throw.
        assertTrue(invoke(new Task()).isEmpty());
    }
}
