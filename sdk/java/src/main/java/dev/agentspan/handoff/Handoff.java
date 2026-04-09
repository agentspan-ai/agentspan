// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.handoff;

/**
 * Base class for condition-based handoff triggers.
 *
 * <p>Handoffs are evaluated when no transfer tool was called and allow the
 * agent to transfer control based on text mentions or tool results.
 *
 * <p>Use {@link OnTextMention} or {@link OnToolResult} to create handoff conditions.
 */
public abstract class Handoff {
    private final String target;

    protected Handoff(String target) {
        this.target = target;
    }

    public String getTarget() {
        return target;
    }
}
