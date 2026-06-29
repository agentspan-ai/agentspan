// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.termination;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

/** Pure unit tests for termination conditions: builders, toMap wire shape, composition. */
class TerminationConditionsTest {

    @Test
    void maxMessage() {
        MaxMessageTermination t = MaxMessageTermination.of(5);
        assertEquals(5, t.getMaxMessages());
        assertEquals("max_message", t.toMap().get("type"));
        assertEquals(5, t.toMap().get("maxMessages"));
    }

    @Test
    void stopMessage() {
        StopMessageTermination t = StopMessageTermination.of("DONE");
        assertEquals("DONE", t.getStopMessage());
        assertEquals("stop_message", t.toMap().get("type"));
    }

    @Test
    void textMention() {
        TextMentionTermination t = TextMentionTermination.of("bye", true);
        assertEquals("bye", t.getText());
        assertTrue(t.isCaseSensitive());
        assertFalse(TextMentionTermination.of("bye").isCaseSensitive());
    }

    @Test
    void andComposition() {
        TerminationCondition and = MaxMessageTermination.of(3).and(StopMessageTermination.of("x"));
        assertInstanceOf(AndTermination.class, and);
        assertNotNull(and.toMap());
    }

    @Test
    void orComposition() {
        TerminationCondition or = MaxMessageTermination.of(3).or(StopMessageTermination.of("x"));
        assertInstanceOf(OrTermination.class, or);
        assertNotNull(or.toMap());
    }

    @Test
    void terminationResult() {
        TerminationResult stop = TerminationResult.stop("done");
        assertTrue(stop.isShouldTerminate());
        assertEquals("done", stop.getReason());
        assertFalse(TerminationResult.continueRunning().isShouldTerminate());
    }
}
