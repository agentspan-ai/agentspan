// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.conductoross.conductor.ai.enums.AgentStatus;
import org.conductoross.conductor.ai.internal.AgentClient;
import org.conductoross.conductor.ai.internal.AgentStatusResponse;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.conductor.client.http.ConductorClient;

/**
 * Unit tests for {@link AgentHandle#waitForResult} error-handling — specifically the
 * consecutive-error fast-fail added to prevent false 600s timeouts.
 */
class AgentHandleErrorTest {

    private static AgentStatusResponse completed(String executionId) {
        try {
            String json = "{\"executionId\":\"" + executionId
                    + "\",\"status\":\"COMPLETED\",\"isComplete\":true,\"isRunning\":false}";
            return new ObjectMapper().readValue(json, AgentStatusResponse.class);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    /** Stub AgentClient that always throws — simulates a permanently-down server. */
    private static AgentClient alwaysErrorClient() {
        return new AgentClient(new ConductorClient("http://localhost:1/api")) {
            @Override
            public AgentStatusResponse getAgentStatus(String executionId) {
                throw new RuntimeException("connection refused");
            }
        };
    }

    /** Stub AgentClient that throws once then returns COMPLETED. */
    private static AgentClient oneErrorThenCompleteClient() {
        AtomicInteger calls = new AtomicInteger(0);
        return new AgentClient(new ConductorClient("http://localhost:1/api")) {
            @Override
            public AgentStatusResponse getAgentStatus(String executionId) {
                if (calls.incrementAndGet() == 1) throw new RuntimeException("transient");
                return completed(executionId);
            }
        };
    }

    /**
     * With the fix: throws after 10 consecutive errors (well under 5s at 1ms poll).
     * COUNTERFACTUAL (no fix): the loop never throws early — it runs until the 600s
     * wall, which @Timeout(5) catches as a test timeout failure, proving the fix matters.
     */
    @Test
    @org.junit.jupiter.api.Timeout(5)
    void consecutiveErrorsFastFail() {
        AgentHandle handle = new AgentHandle("exec-1", alwaysErrorClient(), null);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> handle.waitForResult(600_000, 1));

        assertTrue(
                ex.getMessage().contains("consecutive errors")
                        || ex.getMessage().contains("connection refused"),
                "Exception must mention the root error. Got: " + ex.getMessage()
                        + ". COUNTERFACTUAL: old code threw 'Agent timed out after 600000ms' hiding the cause.");
    }

    @Test
    void singleErrorDoesNotFastFail() {
        AgentHandle handle = new AgentHandle("exec-2", oneErrorThenCompleteClient(), null);
        AgentResult r = assertDoesNotThrow(
                () -> handle.waitForResult(10_000, 1),
                "A single transient error followed by success must still complete normally.");
        assertEquals(AgentStatus.COMPLETED, r.getStatus(), "Status must be COMPLETED after recovery from one error.");
    }
}
