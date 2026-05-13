// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.exceptions;

/**
 * Non-retryable CLI tool failure (e.g. command not found, timeout).
 *
 * <p>When thrown from a CLI tool worker, causes the Conductor task to be marked
 * {@code FAILED_WITH_TERMINAL_ERROR} instead of retrying.
 *
 * <pre>{@code
 * throw new TerminalToolError("Command not found: git");
 * }</pre>
 */
public class TerminalToolError extends RuntimeException {

    public TerminalToolError(String message) {
        super(message);
    }

    public TerminalToolError(String message, Throwable cause) {
        super(message, cause);
    }
}
