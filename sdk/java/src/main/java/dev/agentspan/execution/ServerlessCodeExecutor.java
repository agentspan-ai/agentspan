// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.execution;

/**
 * Base class for remote/serverless code execution services.
 *
 * <p>Extend this class to integrate with custom remote execution endpoints
 * (AWS Lambda, Cloud Run, custom sandboxes, etc.).
 *
 * <pre>{@code
 * class MyExecutor extends ServerlessCodeExecutor {
 *     public MyExecutor() { super("python", 30); }
 *     public ExecutionResult execute(String code) {
 *         // POST code to your remote execution service
 *     }
 * }
 * }</pre>
 */
public abstract class ServerlessCodeExecutor extends CodeExecutor {

    public ServerlessCodeExecutor(String language, int timeout) {
        super(language, timeout, null);
    }

    @Override
    public abstract ExecutionResult execute(String code);
}
