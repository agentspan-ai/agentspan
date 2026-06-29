// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.model;

import java.util.HashMap;
import java.util.Map;

import org.conductoross.conductor.ai.exceptions.CredentialNotFoundException;

/**
 * Context passed to tool functions during execution.
 *
 * <p>Declare a {@code ToolContext} parameter on a {@code @Tool} method and the worker
 * framework injects a per-call instance:
 *
 * <pre>{@code
 * @Tool(credentials = {"GITHUB_TOKEN"})
 * public String fetchIssue(String repo, ToolContext ctx) {
 *     String token = ctx.getCredential("GITHUB_TOKEN");
 *     ...
 * }
 * }</pre>
 *
 * <p>{@link #getState()} provides a mutable dictionary that persists across all tool
 * calls within the same agent execution. Tools can read and write to it to share
 * data without relying on the LLM to relay state (mirrors Python SDK's
 * {@code ToolContext.state}).
 *
 * <p>{@link #getCredential(String)} returns a secret declared in
 * {@code @Tool(credentials = {...})} and resolved by the runtime for this call. The
 * credential map is an immutable per-call snapshot, so it is safe to read from threads
 * the tool spawns — unlike a thread-local, the values remain valid for the lifetime of
 * this context object. See {@code docs/design/secret-injection-contract.md} for the
 * cross-SDK contract; Java's per-call context mirrors .NET's {@code IToolContext} and
 * Python's contextvars accessor.
 */
public class ToolContext {
    private final String sessionId;
    private final String executionId;
    private final String taskId;
    private final Map<String, Object> state;
    private final Map<String, String> credentials;

    public ToolContext(String sessionId, String executionId, String taskId) {
        this(sessionId, executionId, taskId, new HashMap<>());
    }

    public ToolContext(String sessionId, String executionId, String taskId, Map<String, Object> initialState) {
        this(sessionId, executionId, taskId, initialState, null);
    }

    public ToolContext(
            String sessionId,
            String executionId,
            String taskId,
            Map<String, Object> initialState,
            Map<String, String> credentials) {
        this.sessionId = sessionId;
        this.executionId = executionId;
        this.taskId = taskId;
        this.state = initialState != null ? new HashMap<>(initialState) : new HashMap<>();
        // Immutable snapshot: safe to publish to threads the tool spawns.
        this.credentials = (credentials == null || credentials.isEmpty()) ? Map.of() : Map.copyOf(credentials);
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getExecutionId() {
        return executionId;
    }

    public String getTaskId() {
        return taskId;
    }

    /**
     * Shared state dictionary persisted across tool calls within the same agent execution.
     * Mutate this map to pass data to subsequent tool calls.
     */
    public Map<String, Object> getState() {
        return state;
    }

    /**
     * Read a secret declared in {@code @Tool(credentials = {...})} and resolved for this call.
     *
     * @param name the declared credential name
     * @return the plaintext value
     * @throws CredentialNotFoundException if the name was not declared / not resolved for this call
     */
    public String getCredential(String name) {
        String value = credentials.get(name);
        if (value == null) {
            throw new CredentialNotFoundException(name);
        }
        return value;
    }

    /**
     * Read a resolved secret, or {@code null} if it was not declared / not resolved.
     * Use when you want to fall back gracefully instead of failing the tool.
     */
    public String getCredentialOrNull(String name) {
        return credentials.get(name);
    }

    /** An immutable view of all secrets resolved for this call. */
    public Map<String, String> getCredentials() {
        return credentials;
    }
}
