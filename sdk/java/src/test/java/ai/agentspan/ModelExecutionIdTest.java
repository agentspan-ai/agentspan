// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan;

import ai.agentspan.enums.AgentStatus;
import ai.agentspan.enums.EventType;
import ai.agentspan.model.AgentEvent;
import ai.agentspan.model.AgentHandle;
import ai.agentspan.model.AgentResult;
import ai.agentspan.model.ToolContext;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Verify that all public model classes expose {@code getExecutionId()} (not the
 * legacy {@code getWorkflowId()}) — issue #254.
 */
class ModelExecutionIdTest {

    @Test
    void agentResult_getExecutionId() {
        AgentResult result = new AgentResult(
                Map.of("result", "ok"), "exec-123", AgentStatus.COMPLETED,
                List.of(), List.of(), null, null);
        assertEquals("exec-123", result.getExecutionId());
    }

    @Test
    void agentResult_executionId_defaults_to_empty() {
        AgentResult result = new AgentResult(null, null, null, null, null, null, null);
        assertEquals("", result.getExecutionId());
    }

    @Test
    void agentEvent_getExecutionId() {
        AgentEvent event = new AgentEvent(
                EventType.TOOL_CALL, null, "my_tool", Map.of(), null, null,
                "exec-456", null, null);
        assertEquals("exec-456", event.getExecutionId());
    }

    @Test
    void agentEvent_fromMap_reads_executionId_key() {
        Map<String, Object> data = Map.of(
                "type", "tool_call",
                "toolName", "fetch",
                "executionId", "exec-789");
        AgentEvent event = AgentEvent.fromMap(data);
        assertEquals("exec-789", event.getExecutionId());
    }

    @Test
    void toolContext_getExecutionId() {
        ToolContext ctx = new ToolContext("session-1", "exec-abc", "task-1");
        assertEquals("exec-abc", ctx.getExecutionId());
    }

    @Test
    void toolContext_state_is_mutable() {
        ToolContext ctx = new ToolContext("s", "e", "t");
        ctx.getState().put("key", "value");
        assertEquals("value", ctx.getState().get("key"));
    }
}
