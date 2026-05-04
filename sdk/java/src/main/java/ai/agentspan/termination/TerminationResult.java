// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.termination;

/**
 * The result of evaluating a termination condition.
 *
 * <pre>{@code
 * TerminationResult result = new TerminationResult(true, "Max messages reached");
 * if (result.isShouldTerminate()) { ... }
 * }</pre>
 */
public class TerminationResult {

    private final boolean shouldTerminate;
    private final String reason;

    public TerminationResult(boolean shouldTerminate) {
        this(shouldTerminate, null);
    }

    public TerminationResult(boolean shouldTerminate, String reason) {
        this.shouldTerminate = shouldTerminate;
        this.reason = reason;
    }

    public static TerminationResult stop(String reason) {
        return new TerminationResult(true, reason);
    }

    public static TerminationResult continueRunning() {
        return new TerminationResult(false);
    }

    public boolean isShouldTerminate() { return shouldTerminate; }
    public String getReason() { return reason; }

    @Override
    public String toString() {
        return "TerminationResult{shouldTerminate=" + shouldTerminate + ", reason='" + reason + "'}";
    }
}
