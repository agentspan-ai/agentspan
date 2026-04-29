// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.termination;

import java.util.Map;

/**
 * Base class for composable termination conditions.
 *
 * <p>Conditions can be combined with {@link #and(TerminationCondition)} and
 * {@link #or(TerminationCondition)} to build complex logic.
 *
 * <p>Example:
 * <pre>{@code
 * TerminationCondition cond = MaxMessageTermination.of(10)
 *     .or(TextMentionTermination.of("DONE"));
 * }</pre>
 */
public abstract class TerminationCondition {

    /**
     * Combine this condition with another using AND logic.
     * Both conditions must be met for termination.
     */
    public TerminationCondition and(TerminationCondition other) {
        return new AndTermination(this, other);
    }

    /**
     * Combine this condition with another using OR logic.
     * Either condition being met triggers termination.
     */
    public TerminationCondition or(TerminationCondition other) {
        return new OrTermination(this, other);
    }

    /**
     * Serialize this condition to a map for JSON serialization.
     */
    public abstract Map<String, Object> toMap();
}
