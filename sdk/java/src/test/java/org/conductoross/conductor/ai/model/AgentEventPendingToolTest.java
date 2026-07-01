// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;

import org.conductoross.conductor.ai.enums.EventType;
import org.junit.jupiter.api.Test;

/**
 * Regression test for issue #226. {@link AgentEvent#fromMap(Map)} must surface
 * the {@code pendingTool} block of a {@code waiting} SSE event so callers can
 * tell which tool(s) are awaiting approval.
 *
 * <p>One HUMAN task gates a batch of tool calls with a single {@code
 * {approved, reason}} verdict — so the array is the load-bearing field; the
 * legacy singular {@code tool_name} / {@code parameters} keys remain null
 * and consumers must iterate {@link AgentEvent#getPendingToolCalls()}.
 */
class AgentEventPendingToolTest {

    @Test
    void fromMap_surfacesPendingToolMapOnWaitingEvent() {
        Map<String, Object> wire = Map.of(
                "type", "waiting",
                "executionId", "wf-1",
                "pendingTool",
                        Map.of(
                                "taskRefName",
                                "agent_approval_human",
                                "toolCalls",
                                List.of(
                                        Map.of("name", "publish_article", "args", Map.of("title", "Test")),
                                        Map.of("name", "send_email", "args", Map.of("to", "ops@example.com")))));

        AgentEvent event = AgentEvent.fromMap(wire);

        assertEquals(EventType.WAITING, event.getType());
        Map<String, Object> pendingTool = event.getPendingTool();
        assertNotNull(pendingTool, "pendingTool must be surfaced for waiting events");
        assertEquals("agent_approval_human", pendingTool.get("taskRefName"));

        List<PendingToolCall> calls = event.getPendingToolCalls();
        assertNotNull(calls, "getPendingToolCalls() must parse the toolCalls array");
        assertEquals(2, calls.size());
        assertEquals("publish_article", calls.get(0).getName());
        assertEquals(Map.of("title", "Test"), calls.get(0).getArgs());
        assertEquals("send_email", calls.get(1).getName());
        assertEquals(Map.of("to", "ops@example.com"), calls.get(1).getArgs());
    }

    @Test
    void fromMap_returnsEmptyPendingToolCallsWhenNoneEmitted() {
        Map<String, Object> wire = Map.of(
                "type", "waiting",
                "executionId", "wf-2",
                "pendingTool", Map.of("taskRefName", "agent_approval_human"));

        AgentEvent event = AgentEvent.fromMap(wire);

        assertNotNull(event.getPendingTool());
        assertTrue(
                event.getPendingToolCalls().isEmpty(),
                "pendingToolCalls is an empty list (never null) when the server emits no toolCalls");
    }

    @Test
    void fromMap_returnsNullPendingToolForNonWaitingEvents() {
        Map<String, Object> wire = Map.of(
                "type", "thinking",
                "executionId", "wf-3",
                "content", "agent_llm");

        AgentEvent event = AgentEvent.fromMap(wire);

        assertEquals(EventType.THINKING, event.getType());
        assertNull(event.getPendingTool());
        assertTrue(event.getPendingToolCalls().isEmpty());
    }
}
