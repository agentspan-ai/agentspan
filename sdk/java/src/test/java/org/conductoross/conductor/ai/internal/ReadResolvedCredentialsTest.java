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

/**
 * Validates {@code WorkerManager.readResolvedCredentials} — the embedded host-delivery read-path
 * that extracts {@code __resolved_credentials__} (resolved by the host from
 * {@code ${workflow.secrets.NAME}}) from task input. Absent/empty → empty map (standalone falls
 * back to the native token-pull).
 */
class ReadResolvedCredentialsTest {

    @SuppressWarnings("unchecked")
    private static Map<String, String> invoke(Map<String, Object> inputData) throws Exception {
        Method m = WorkerManager.class.getDeclaredMethod("readResolvedCredentials", Map.class);
        m.setAccessible(true);
        return (Map<String, String>) m.invoke(null, inputData);
    }

    @Test
    void extractsHostDeliveredStringValues() throws Exception {
        Map<String, Object> rc = new HashMap<>();
        rc.put("GITHUB_TOKEN", "ghp_host");
        rc.put("NOT_A_STRING", 123); // non-string values are skipped
        Map<String, Object> input = new HashMap<>();
        input.put("__resolved_credentials__", rc);

        Map<String, String> out = invoke(input);

        assertEquals(1, out.size());
        assertEquals("ghp_host", out.get("GITHUB_TOKEN"));
    }

    @Test
    void emptyWhenKeyAbsentOrNull() throws Exception {
        assertTrue(invoke(new HashMap<>()).isEmpty());
        assertTrue(invoke(null).isEmpty());
        Map<String, Object> emptyMap = new HashMap<>();
        emptyMap.put("__resolved_credentials__", new HashMap<>());
        assertTrue(invoke(emptyMap).isEmpty());
    }
}
