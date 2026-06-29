// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.internal;

import org.conductoross.conductor.ai.exceptions.AgentAPIException;
import org.conductoross.conductor.ai.exceptions.AgentNotFoundException;
import org.conductoross.conductor.ai.model.CompileResponse;

import com.fasterxml.jackson.core.type.TypeReference;
import com.netflix.conductor.client.exception.ConductorClientException;
import com.netflix.conductor.client.http.ConductorClient;
import com.netflix.conductor.client.http.ConductorClientRequest;
import com.netflix.conductor.client.http.ConductorClientRequest.Method;
import com.netflix.conductor.client.http.ConductorClientResponse;

/**
 * Client for agentspan's proprietary agent control-plane ({@code /api/agent/*}).
 *
 * <p>Strictly scoped to five endpoints — compile, deploy, start, status, respond.
 * Standard Conductor endpoints ({@code /api/workflow/*}, {@code /api/tasks}, etc.)
 * are handled by the Conductor SDK's own typed clients ({@code WorkflowClient},
 * {@code TaskClient}, {@code MetadataClient}).
 *
 * <p>Every request goes through the shared {@link ConductorClient}'s native HTTP +
 * auth + serialization layer ({@link ConductorClientRequest} →
 * {@link ConductorClient#execute}). No hand-rolled HTTP. Conductor's
 * {@link ConductorClientException} is mapped to agentspan's
 * {@link AgentAPIException}/{@link AgentNotFoundException}.
 *
 * <p>Paths are relative to the client's base path (the server's {@code /api}
 * root), so {@code "/agent/start"} resolves to {@code /api/agent/start}.
 */
public class AgentClient {

    private static final TypeReference<CompileResponse> COMPILE_TYPE = new TypeReference<CompileResponse>() {};
    private static final TypeReference<StartResponse> START_TYPE = new TypeReference<StartResponse>() {};
    private static final TypeReference<AgentStatusResponse> STATUS_TYPE = new TypeReference<AgentStatusResponse>() {};

    protected final ConductorClient client;

    public AgentClient(ConductorClient client) {
        this.client = client;
    }

    /** {@code POST /api/agent/compile} — compile agent config to a workflow def. */
    public CompileResponse compileAgent(AgentRequest request) {
        return post("/agent/compile", request, COMPILE_TYPE);
    }

    /** {@code POST /api/agent/deploy} — compile + register, no execution. */
    public StartResponse deployAgent(AgentRequest request) {
        return post("/agent/deploy", request, START_TYPE);
    }

    /** {@code POST /api/agent/start} — compile + register + start an execution. */
    public StartResponse startAgent(AgentRequest request) {
        return post("/agent/start", request, START_TYPE);
    }

    /** {@code GET /api/agent/{executionId}/status} — fetch execution status. */
    public AgentStatusResponse getAgentStatus(String executionId) {
        ConductorClientRequest req = ConductorClientRequest.builder()
                .method(Method.GET)
                .path("/agent/{executionId}/status")
                .addPathParam("executionId", executionId)
                .build();
        return executeFor(req, STATUS_TYPE);
    }

    /** {@code POST /api/agent/{executionId}/respond} — respond to a waiting HITL task. */
    public void respond(String executionId, RespondBody body) {
        ConductorClientRequest req = ConductorClientRequest.builder()
                .method(Method.POST)
                .path("/agent/{executionId}/respond")
                .addPathParam("executionId", executionId)
                .body(body)
                .build();
        try {
            client.execute(req);
        } catch (ConductorClientException e) {
            throw mapException(e);
        }
    }

    // ── internals ──────────────────────────────────────────────────────────

    private <T> T post(String path, Object payload, TypeReference<T> type) {
        ConductorClientRequest req = ConductorClientRequest.builder()
                .method(Method.POST)
                .path(path)
                .body(payload)
                .build();
        return executeFor(req, type);
    }

    private <T> T executeFor(ConductorClientRequest req, TypeReference<T> type) {
        try {
            ConductorClientResponse<T> resp = client.execute(req, type);
            return resp.getData();
        } catch (ConductorClientException e) {
            throw mapException(e);
        }
    }

    /** Preserve agentspan's typed error contract over Conductor's exception. */
    private static RuntimeException mapException(ConductorClientException e) {
        int status = e.getStatus();
        String body = e.getMessage();
        if (status == 404) {
            return new AgentNotFoundException(status, body);
        }
        return new AgentAPIException(status, body);
    }
}
