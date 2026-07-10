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
 * Validates {@code WorkerManager.readRuntimeMetadata} — the embedded host-delivery read-path that
 * extracts the host-resolved secret values from {@code Task.runtimeMetadata} (wire-only, resolved by
 * the host from the worker's declared {@code TaskDef.runtimeMetadata}; conductor-oss PR #1255).
 * Absent/empty → empty map (standalone falls back to the native token-pull).
 */
class ReadRuntimeMetadataTest {

    @SuppressWarnings("unchecked")
    private static Map<String, String> invoke(Task task) throws Exception {
        Method m = WorkerManager.class.getDeclaredMethod("readRuntimeMetadata", Task.class);
        m.setAccessible(true);
        return (Map<String, String>) m.invoke(null, task);
    }

    private static Task taskWithRuntimeMetadata(Map<String, String> rm) {
        Task task = new Task();
        task.setRuntimeMetadata(rm);
        return task;
    }

    @Test
    void extractsHostDeliveredValues() throws Exception {
        Map<String, String> rm = new HashMap<>();
        rm.put("GITHUB_TOKEN", "ghp_host");
        rm.put("GH_APP_ID", "42");

        Map<String, String> out = invoke(taskWithRuntimeMetadata(rm));

        assertEquals(2, out.size());
        assertEquals("ghp_host", out.get("GITHUB_TOKEN"));
        assertEquals("42", out.get("GH_APP_ID"));
    }

    @Test
    void emptyWhenAbsentOrEmpty() throws Exception {
        assertTrue(invoke(null).isEmpty());
        assertTrue(invoke(new Task()).isEmpty());
        assertTrue(invoke(taskWithRuntimeMetadata(new HashMap<>())).isEmpty());
    }
}
