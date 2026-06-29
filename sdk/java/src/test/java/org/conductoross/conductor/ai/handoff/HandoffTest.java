// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.handoff;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;

/** Pure unit tests for handoff routing rules. */
class HandoffTest {

    @Test
    void textMentionCapturesTriggerAndTarget() {
        OnTextMention h = OnTextMention.of("reverse", "text_agent");
        assertEquals("reverse", h.getText());
        assertEquals("text_agent", h.getTarget());
    }

    @Test
    void toolResultWithContains() {
        OnToolResult h = OnToolResult.of("calc", "math_agent", "42");
        assertEquals("calc", h.getToolName());
        assertEquals("math_agent", h.getTarget());
        assertEquals("42", h.getResultContains());
    }

    @Test
    void toolResultTwoArg() {
        OnToolResult h = OnToolResult.of("calc", "math_agent");
        assertEquals("calc", h.getToolName());
        assertEquals("math_agent", h.getTarget());
    }

    @Test
    void onConditionPredicateEvaluates() {
        OnCondition h = new OnCondition("router", m -> "go".equals(m.get("k")));
        assertEquals("router", h.getTarget());
        assertTrue(h.getCondition().apply(Map.of("k", "go")));
        assertFalse(h.getCondition().apply(Map.of("k", "stop")));
    }
}
