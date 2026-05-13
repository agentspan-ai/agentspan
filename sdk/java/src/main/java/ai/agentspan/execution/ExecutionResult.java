// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.execution;

/** The result of a code execution. */
public class ExecutionResult {

    private final String output;
    private final String error;
    private final int exitCode;
    private final boolean timedOut;

    public ExecutionResult(String output, String error, int exitCode, boolean timedOut) {
        this.output = output != null ? output : "";
        this.error = error != null ? error : "";
        this.exitCode = exitCode;
        this.timedOut = timedOut;
    }

    /** Standard output from the execution. */
    public String getOutput() { return output; }

    /** Standard error output (if any). */
    public String getError() { return error; }

    /** Process exit code (0 = success). */
    public int getExitCode() { return exitCode; }

    /** {@code true} if execution was killed due to timeout. */
    public boolean isTimedOut() { return timedOut; }

    /** {@code true} if the execution succeeded (exit code 0, no timeout). */
    public boolean isSuccess() { return exitCode == 0 && !timedOut; }
}
